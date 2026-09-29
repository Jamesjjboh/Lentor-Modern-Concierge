"""Telegram Bot interface for Lentor Modern AI Concierge.
Supports 1-on-1 resident chats, interactive admin moderation, broadcast engine, and analytics.
Runs via long-polling in local development, and supports webhook for Cloud Run deployment.
"""

import logging
import os
from telegram import Chat, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from src.admin import (
    handle_admin_stats_command,
    handle_broadcast_command,
    handle_moderation_callback,
    notify_admin_new_tip,
)
from src.agent import concierge_agent, submit_tip_to_moderation
from src.config import ENVIRONMENT, PORT, TELEGRAM_BOT_TOKEN, WEBHOOK_URL
from src.database import db_client

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /start command, registers resident, and provides concierge onboarding."""
    user = update.effective_user
    if not user or not update.message:
        return

    # Register user in Firestore
    db_client.get_or_create_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )

    welcome_text = (
        f"👋 Welcome to the *Lentor Modern AI Concierge*, {user.first_name or 'Resident'}!\n\n"
        f"I am your 24/7 autonomous resident assistant for ~605 households at Lentor Modern.\n\n"
        f"Here are a few things you can ask me:\n"
        f"• 📜 *Estate By-laws:* _\"What are the renovation hours and deposit fees?\"_\n"
        f"• 🔑 *Access & Utilities:* _\"How do I get the fiber broadband riser key for NetLink?\"_\n"
        f"• 🏬 *Mall Directory:* _\"What time does CS Fresh close? Is there a clinic on L1?\"_\n"
        f"• 💡 *Neighbour Tips:* _\"Where should Taobao delivery trucks enter?\"_\n"
        f"• ✉️ *MA Drafting:* _\"Help me draft an email to the MA about corridor noise.\"_\n\n"
        f"💡 *Have a tip for neighbours?* Submit it anytime with:\n"
        f"`/tip <topic> <your tip>` (e.g. `/tip mall CS Fresh sushi 20% off after 8:30pm`)\n\n"
        f"How can I assist you today?"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /help command."""
    if not update.message:
        return

    help_text = (
        "🤖 *Lentor Modern Concierge Commands:*\n\n"
        "• Just message me directly with any question about estate rules, facilities, or mall shops.\n"
        "• `/tip <topic> <advice>` — Submit a community tip for admin review.\n"
        "• `/help` — View this assistance message.\n\n"
        "*Admin Commands:*\n"
        "• `/broadcast <message>` — Send estate broadcast to registered residents.\n"
        "• `/admin_stats` — View resident activity and content gaps."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def tip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allows residents to explicitly submit a community tip via `/tip <topic> <content>`."""
    user = update.effective_user
    if not user or not update.message:
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Format: `/tip <topic> <your tip>`\nExample: `/tip wifi Ask security for Tower 1 riser key early`",
            parse_mode="Markdown",
        )
        return

    topic = context.args[0]
    tip_content = " ".join(context.args[1:])

    tip_id = db_client.submit_community_tip(user_id=user.id, topic=topic, content=tip_content)
    
    # Notify admin with interactive approval buttons
    await notify_admin_new_tip(context, tip_id=tip_id, topic=topic, content=tip_content)

    await update.message.reply_text(
        f"✅ Thank you! Your tip about *{topic}* has been submitted for review. Once verified, it will be added to the resident knowledge base.",
        parse_mode="Markdown",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes incoming 1-on-1 resident messages through the Gemini 3.8 Flash Agent."""
    user = update.effective_user
    message = update.message
    if not user or not message or not message.text:
        return

    # Guardrail: Encourage 1-on-1 usage
    if update.effective_chat and update.effective_chat.type != Chat.PRIVATE:
        await message.reply_text("Please chat with me directly in a 1-on-1 private message to protect resident privacy!")
        return

    user_query = message.text.strip()
    
    # Register / update user activity
    db_client.get_or_create_user(user_id=user.id, username=user.username, first_name=user.first_name)
    db_client.increment_user_query(user_id=user.id)

    # Show Telegram typing indicator
    await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)

    # Execute autonomous agent query
    response_text, tools_called = concierge_agent.run_query(user_query=user_query, user_id=user.id)

    # Log query into Firestore for content gap detection
    answered_successfully = not ("I don't know" in response_text or "No official by-laws found" in response_text)
    db_client.log_query(
        user_id=user.id,
        user_query=user_query,
        tools_called=tools_called,
        agent_response=response_text,
        answered_successfully=answered_successfully,
    )

    # If the agent called submit_tip_to_moderation, find the tip and alert admin
    if "submit_tip_to_moderation" in tools_called:
        # Check if there is an unreviewed pending tip from this user
        pending_tips = [
            t for t in getattr(db_client, "_mock_tips", {}).values()
            if t.get("submitted_by_user_id") == str(user.id) and t.get("status") == "pending"
        ]
        if pending_tips:
            latest = pending_tips[-1]
            await notify_admin_new_tip(
                context,
                tip_id=latest.get("tip_id", ""),
                topic=latest.get("topic", "community"),
                content=latest.get("content", ""),
            )

    await message.reply_text(response_text)


def create_bot_app() -> Application:
    """Builds and configures the python-telegram-bot application."""
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN is not configured in .env. Bot cannot start without token.")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN or "MOCK_TOKEN").build()

    # Command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("tip", tip_command))
    app.add_handler(CommandHandler("broadcast", handle_broadcast_command))
    app.add_handler(CommandHandler("admin_stats", handle_admin_stats_command))

    # Callback handler for admin interactive inline moderation buttons
    app.add_handler(CallbackQueryHandler(handle_moderation_callback, pattern=r"^mod_"))

    # Default message handler for 1-on-1 resident chats
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return app


def main():
    """Starts the bot via long-polling (dev) or webhook (Cloud Run production)."""
    if not TELEGRAM_BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN is not set. Please copy .env.example to .env and configure your token.")
        return

    app = create_bot_app()

    if WEBHOOK_URL:
        logger.info(f"Starting bot in Webhook mode on port {PORT} with URL {WEBHOOK_URL}")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TELEGRAM_BOT_TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{TELEGRAM_BOT_TOKEN}",
        )
    else:
        logger.info("Starting bot in local polling mode...")
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
