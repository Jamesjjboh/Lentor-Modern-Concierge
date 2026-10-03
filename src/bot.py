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
from telegram.request import HTTPXRequest


import re

from src.admin import (
    handle_admin_stats_command,
    handle_broadcast_command,
    handle_feedback_callback,
    handle_moderation_callback,
    handle_reply_command,
    is_admin,
    notify_admin_new_feedback,
    notify_admin_new_tip,
)
from src.agent import concierge_agent, submit_tip_to_moderation
from src.config import ADMIN_TELEGRAM_ID, ENVIRONMENT, PORT, TELEGRAM_BOT_TOKEN, WEBHOOK_URL
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
        f"👋 Welcome to the *Lentor Modern Digital Concierge*, {user.first_name or 'Resident'}!\n\n"
        f"I am your 24/7 digital resident companion for Lentor Modern. You can ask me anything about "
        f"estate by-laws, facility bookings, mall directory, or crowdsourced neighbour tips.\n\n"
        f"Here are a few common things you can do:\n"
        f"• 🔨 *Renovations:* _\"What are the renovation working hours and deposit amounts?\"_\n"
        f"• 🚚 *Deliveries & Moving:* _\"Where is the residential loading bay and what is the height limit?\"_\n"
        f"• 🏬 *Mall Directory:* _\"What time does CS Fresh close? Is there a clinic in the mall?\"_\n"
        f"• 🏊 *Facilities & Parking:* _\"What are the gym hours and BBQ booking rules?\"_\n"
        f"• 🛠️ *Defects & Inquiries:* _\"How do I report common property defects or contact the Managing Agent?\"_\n"
        f"• 📸 *Photo Assistance:* _Send a photo of an appliance error code, or snap a notice board to ask a question!_\n\n"
        f"💡 *Got a helpful tip for your neighbours?*\n"
        f"Snap a photo of any mall promo or notice, or type:\n"
        f"`/tip <topic> <your tip>` (e.g. `/tip mall CS Fresh sushi discounts start after 8:30pm`)\n\n"
        f"🛠️ *Feedback or Bug Report?*\n"
        f"Help improve this bot! Type `/feedback <suggestion>` or `/bug <issue>` to message the developer (@jamesjjboh) directly.\n\n"
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
        "• `/feedback <suggestion>` — Send feature ideas or feedback directly to developer @jamesjjboh.\n"
        "• `/bug <issue>` — Report an inaccurate answer or technical bug.\n"
        "• `/help` — View this assistance message.\n\n"
        "*Admin Commands:*\n"
        "• `/reply <user_id> <message>` — Send direct message to a resident.\n"
        "• `/broadcast <message>` — Send estate broadcast to registered residents.\n"
        "• `/admin_stats` — View resident activity, feedback, and content gaps."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def tip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allows residents to explicitly submit a community tip via `/tip <topic> <content>`."""
    user = update.effective_user
    if not user or not update.message:
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Format: `/tip <topic> <your tip>`\nExample: `/tip mall CS Fresh sushi discounts start after 8:30pm`",
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


async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allows residents to submit feature ideas or general feedback to the developer."""
    user = update.effective_user
    message = update.message
    if not user or not message:
        return

    if update.effective_chat and update.effective_chat.type != Chat.PRIVATE:
        await message.reply_text("Please message me in a 1-on-1 private chat to submit feedback!")
        return

    db_client.get_or_create_user(user_id=user.id, username=user.username, first_name=user.first_name)

    if not context.args:
        await message.reply_text(
            "💡 *How to share feedback or feature ideas:*\n\n"
            "Type `/feedback <your idea or suggestion>`\n"
            "Example: `/feedback Could you add Lentor MRT train arrival timings?`\n\n"
            "You can also attach a screenshot with the caption `/feedback`!",
            parse_mode="Markdown",
        )
        return

    feedback_text = " ".join(context.args)
    category = "feature_request" if any(w in feedback_text.lower() for w in ["feature", "add", "can you", "could you"]) else "general"

    fb_id = db_client.submit_feedback(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        category=category,
        message=feedback_text,
    )

    await notify_admin_new_feedback(
        context=context,
        feedback_id=fb_id,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        category=category,
        message=feedback_text,
    )

    await message.reply_text(
        "🙏 *Thank you for your feedback!*\n\n"
        "Your suggestion has been delivered directly to the project developer (@jamesjjboh). "
        "We continuously improve the Lentor Modern Concierge based on resident input.",
        parse_mode="Markdown",
    )


async def bug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allows residents to report incorrect answers, hallucinations, or bugs."""
    user = update.effective_user
    message = update.message
    if not user or not message:
        return

    if update.effective_chat and update.effective_chat.type != Chat.PRIVATE:
        await message.reply_text("Please message me in a 1-on-1 private chat to report bugs!")
        return

    db_client.get_or_create_user(user_id=user.id, username=user.username, first_name=user.first_name)

    if not context.args:
        await message.reply_text(
            "🐛 *How to report a bug or incorrect information:*\n\n"
            "Type `/bug <details of the issue>`\n"
            "Example: `/bug The gym opening hour is actually 6:00 AM on weekdays.`\n\n"
            "You can also attach a screenshot with the caption `/bug`!",
            parse_mode="Markdown",
        )
        return

    bug_text = " ".join(context.args)
    category = "data_correction" if any(w in bug_text.lower() for w in ["wrong", "hour", "time", "incorrect", "actually"]) else "bug"

    fb_id = db_client.submit_feedback(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        category=category,
        message=bug_text,
    )

    await notify_admin_new_feedback(
        context=context,
        feedback_id=fb_id,
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        category=category,
        message=bug_text,
    )

    await message.reply_text(
        "🛠️ *Thank you for reporting this issue!*\n\n"
        "Your report has been dispatched directly to developer @jamesjjboh to investigate and patch.",
        parse_mode="Markdown",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes incoming 1-on-1 resident messages through the Gemini 3.8 Flash Agent."""
    user = update.effective_user
    message = update.message
    if not user or not message or not message.text:
        return

    # Admin Swipe-to-Reply or ForceReply intercept
    if is_admin(user.id) and message.reply_to_message:
        replied_msg = message.reply_to_message
        mapping = db_client.get_admin_reply_mapping(replied_msg.message_id)
        target_user_id = None
        target_name = "Resident"
        feedback_id = None

        if mapping:
            target_user_id = int(mapping["user_id"])
            target_name = mapping.get("resident_name", "Resident")
            feedback_id = mapping.get("feedback_id")
        else:
            # Fallback regex extraction from text or caption: User ID: `12345678`
            content_to_check = replied_msg.text or replied_msg.caption or ""
            match = re.search(r"User ID:\*? `?(\d+)`?", content_to_check)
            if match:
                target_user_id = int(match.group(1))

        if target_user_id:
            admin_reply_text = message.text.strip()
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text=(
                        f"📩 *Message from Developer (@jamesjjboh):*\n\n"
                        f"\"{admin_reply_text}\""
                    ),
                    parse_mode="Markdown",
                )
                if feedback_id:
                    db_client.update_feedback_status(
                        feedback_id=feedback_id,
                        status="replied",
                        admin_reply=admin_reply_text,
                    )
                await message.reply_text(
                    f"✅ *Reply successfully delivered to {target_name} (`{target_user_id}`)!*",
                    parse_mode="Markdown",
                )
                return
            except Exception as e:
                logger.error(f"Failed to forward admin reply to {target_user_id}: {e}")
                await message.reply_text(f"⚠️ Failed to deliver reply to user `{target_user_id}`: {e}")
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

    # If the agent called submit_developer_feedback, alert admin
    if "submit_developer_feedback" in tools_called:
        await notify_admin_new_feedback(
            context=context,
            feedback_id="agent_fb",
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            category="chat_feedback",
            message=user_query,
        )

    await message.reply_text(response_text)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes incoming photos from residents (tips, feedback, or visual inquiries) via Gemini Vision."""
    user = update.effective_user
    message = update.message
    if not user or not message or not message.photo:
        return

    # Guardrail: Encourage 1-on-1 usage
    if update.effective_chat and update.effective_chat.type != Chat.PRIVATE:
        await message.reply_text("Please chat with me directly in a 1-on-1 private message to protect resident privacy!")
        return

    # Register user activity
    db_client.get_or_create_user(user_id=user.id, username=user.username, first_name=user.first_name)
    db_client.increment_user_query(user_id=user.id)

    # Indicate processing
    await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)

    caption = message.caption or ""
    highest_res_photo = message.photo[-1]

    try:
        tg_file = await highest_res_photo.get_file()
        photo_bytes = await tg_file.download_as_bytearray()
    except Exception as e:
        logger.error(f"Failed to download photo from user {user.id}: {e}")
        await message.reply_text("Sorry, I had trouble downloading your photo. Please try sending it again.")
        return

    # Multimodal image analysis using Gemini 3.8 Flash Vision
    result = concierge_agent.analyze_resident_image(
        image_bytes=bytes(photo_bytes),
        caption=caption,
        user_id=user.id,
    )

    intent = result.get("intent", "RESIDENT_QUESTION")
    topic = result.get("topic", "general")
    title = result.get("title", "Photo Discovery")
    tip_content = result.get("tip", "")
    user_reply = result.get("user_reply", "Thank you for sharing your photo!")

    if intent == "TIP_SUBMISSION" and tip_content:
        # Submit to moderation queue
        tip_id = db_client.submit_community_tip(
            user_id=user.id,
            topic=topic,
            content=tip_content,
            has_image=True,
            image_summary=title,
        )

        # Notify Admin with photo + interactive approve/reject buttons
        await notify_admin_new_tip(
            context,
            tip_id=tip_id,
            topic=topic,
            content=f"📸 [{title}]\n{tip_content}",
            photo_bytes=bytes(photo_bytes),
        )

        # Log query
        db_client.log_query(
            user_id=user.id,
            user_query=f"[Photo Tip Submission] {caption}",
            tools_called=["analyze_resident_image", "submit_tip_to_moderation"],
            agent_response=user_reply,
            answered_successfully=True,
        )
    elif intent == "FEEDBACK_SUBMISSION" or any(k in caption.lower() for k in ["/feedback", "/bug"]):
        # Submit to resident feedback queue
        category = "bug" if "/bug" in caption.lower() or topic == "bug" else "feature_request"
        fb_id = db_client.submit_feedback(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            category=category,
            message=tip_content or caption or title,
            has_image=True,
            image_summary=title,
        )

        # Notify Admin with photo + swipe-to-reply / tap-to-reply buttons
        await notify_admin_new_feedback(
            context=context,
            feedback_id=fb_id,
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            category=category,
            message=f"📸 [{title}]\n{tip_content or caption or 'Resident attached a screenshot/photo.'}",
            photo_bytes=bytes(photo_bytes),
        )

        # Log query
        db_client.log_query(
            user_id=user.id,
            user_query=f"[Photo Feedback] {caption}",
            tools_called=["analyze_resident_image", "submit_developer_feedback"],
            agent_response=user_reply,
            answered_successfully=True,
        )
    else:
        # Visual query / troubleshooting
        db_client.log_query(
            user_id=user.id,
            user_query=f"[Photo Query] {caption}",
            tools_called=["analyze_resident_image"],
            agent_response=user_reply,
            answered_successfully=True,
        )

    await message.reply_text(user_reply)


def create_bot_app() -> Application:
    """Builds and configures the python-telegram-bot application."""
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN is not configured in .env. Bot cannot start without token.")

    request = HTTPXRequest(connect_timeout=30.0, read_timeout=30.0)
    app = Application.builder().token(TELEGRAM_BOT_TOKEN or "MOCK_TOKEN").request(request).build()


    # Command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("tip", tip_command))
    app.add_handler(CommandHandler("feedback", feedback_command))
    app.add_handler(CommandHandler("bug", bug_command))
    app.add_handler(CommandHandler("reply", handle_reply_command))
    app.add_handler(CommandHandler("broadcast", handle_broadcast_command))
    app.add_handler(CommandHandler("admin_stats", handle_admin_stats_command))

    # Callback handler for admin interactive inline moderation buttons
    app.add_handler(CallbackQueryHandler(handle_moderation_callback, pattern=r"^mod_"))
    app.add_handler(CallbackQueryHandler(handle_feedback_callback, pattern=r"^fb_"))

    # Photo handler for resident tip submissions and visual inquiries
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Default message handler for 1-on-1 resident chats
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    return app



def main():
    """Starts the bot via long-polling (dev) or webhook (Cloud Run production)."""
    if not TELEGRAM_BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN is not set. Please copy .env.example to .env and configure your token.")
        return

    app = create_bot_app()

    if ENVIRONMENT == "production" or WEBHOOK_URL:
        full_webhook_url = f"{WEBHOOK_URL}/{TELEGRAM_BOT_TOKEN}" if WEBHOOK_URL else None
        logger.info(f"🌐 Running in Webhook Mode on port {PORT}...")
        if full_webhook_url:
            logger.info(f"🔗 Setting Telegram Webhook to: {full_webhook_url}")
            app.run_webhook(
                listen="0.0.0.0",
                port=PORT,
                url_path=TELEGRAM_BOT_TOKEN,
                webhook_url=full_webhook_url,
            )
        else:
            app.run_webhook(
                listen="0.0.0.0",
                port=PORT,
                url_path=TELEGRAM_BOT_TOKEN,
            )
    else:
        logger.info("💻 Running in local polling mode...")
        app.run_polling(drop_pending_updates=True)



if __name__ == "__main__":
    main()
