"""Telegram Bot interface for Lentor Modern AI Concierge.
Supports 1-on-1 resident chats, interactive admin moderation, broadcast engine, and analytics.
Runs via long-polling in local development, and supports webhook for Cloud Run deployment.
"""

import logging
import os
from telegram import Chat, InlineKeyboardButton, InlineKeyboardMarkup, Update
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


def get_quick_menu_keyboard() -> InlineKeyboardMarkup:
    """Returns the 6-button interactive 1-tap quick action keyboard for residents."""
    keyboard = [
        [
            InlineKeyboardButton("🏢 Estate Contacts", callback_data="menu_contacts"),
            InlineKeyboardButton("🏊 Facilities & Gym", callback_data="menu_facilities"),
        ],
        [
            InlineKeyboardButton("🚇 Transit & Buses", callback_data="menu_transit"),
            InlineKeyboardButton("🏬 Mall & Deals", callback_data="menu_mall"),
        ],
        [
            InlineKeyboardButton("🔨 Moving & Reno", callback_data="menu_reno"),
            InlineKeyboardButton("📱 iPlus Living Guide", callback_data="menu_iplus"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """Returns a Back to Quick Menu button."""
    return InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Quick Menu", callback_data="menu_main")]])


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /start command, registers resident, and provides concierge onboarding with 1-tap quick actions."""
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
        f"I am your 24/7 resident companion for Lentor Modern. You can chat with me naturally in plain text, "
        f"send photos of notices/defects, or tap below for instant 1-tap resident shortcuts:\n\n"
        f"• 🔨 *Renovations:* _\"What are the renovation working hours and deposit amounts?\"_\n"
        f"• 🚚 *Deliveries & Moving:* _\"Where is the residential loading bay and what is the height limit?\"_\n"
        f"• 🏬 *Mall Directory:* _\"What time does CS Fresh close? Is there a clinic in the mall?\"_\n"
        f"• 🏊 *Facilities & Gym:* _\"What are the gym hours and BBQ booking rules?\"_\n"
        f"• 🚇 *Transit & Bus:* _\"What time is the last train to Woodlands or Bayshore?\"_\n"
        f"• 📸 *Photo Inquiries:* _Send a photo of an appliance error code or snap a notice board!_\n\n"
        f"Tap an option below to start immediately:"
    )
    await update.message.reply_text(
        welcome_text,
        reply_markup=get_quick_menu_keyboard(),
        parse_mode="Markdown",
    )


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /menu command, displaying the interactive 1-tap quick action menu."""
    if not update.message:
        return
    await update.message.reply_text(
        "🛎️ *Lentor Modern Quick Actions Menu:*\nTap any topic below for instant information:",
        reply_markup=get_quick_menu_keyboard(),
        parse_mode="Markdown",
    )


async def handle_quick_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles 1-tap interactive menu selections instantly without consuming LLM tokens."""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    action = query.data
    user = query.from_user

    if action == "menu_main":
        main_text = (
            f"👋 *Lentor Modern Quick Actions Menu:*\n\n"
            f"Select any topic below for instant information, or type your question below:"
        )
        await query.edit_message_text(
            text=main_text,
            reply_markup=get_quick_menu_keyboard(),
            parse_mode="Markdown",
        )
        return

    back_markup = get_back_to_menu_keyboard()

    if action == "menu_contacts":
        text = (
            "🏢 *Primary On-Site Estate Contacts:*\n\n"
            "• *Managing Agent (CBRE):*\n"
            "  📍 9 Lentor Central, Level 3\n"
            "  📞 `+65 6054 3370` (Mon–Fri 9am–6pm, Sat 9am–1pm)\n"
            "  ✉️ `managementoffice@LT-MODERN.COM`\n\n"
            "• *Residential Concierge Desk (24/7):*\n"
            "  📞 `+65 6054 3375` | ✉️ `concierge@LT-MODERN.COM`\n\n"
            "• *Security Control Room (24/7 Emergency):*\n"
            "  📞 `+65 6054 3379`\n\n"
            "• *Developer CST (Defects & Novade Support):*\n"
            "  📞 `6433 9342` | ✉️ `LMcustomerservice@lentormodern.com.sg`\n"
            "  Main Contractor: Lian Beng Construction (1988) Pte Ltd"
        )
    elif action == "menu_facilities":
        text = (
            "🏊 *Recreational Facilities Guide:*\n\n"
            "• 🏋️ *Indoor Gym (Level 4 Clubhouse):* *6:00 AM – 10:00 PM daily*\n"
            "  _Extended from 8am for morning workouts! Automated door access cuts off at 10pm sharp._\n"
            "• 🏊 *50m Lap Pool & Pools (Level 4):* 7:00 AM – 10:00 PM daily\n"
            "• 🎾 *Tennis Court (Level 4):* 8:00 AM – 10:00 PM (Book via iPlus Living)\n"
            "• 🍖 *Sky Dining & BBQ Pavilions (Level 14):* Closes 10:00 PM (Book via iPlus Living)\n"
            "• 🎱 *Clubhouse Function Room (Level 4):* Closes 10:00 PM (Book via iPlus Living)\n"
            "• 🚗 *Car Washing Bays (Level 3 Carpark):* Lots 245, 259, 292 (Water tap key from Concierge)"
        )
    elif action == "menu_transit":
        text = (
            "🚇 *Transit & Bus Guide (Lentor TE5):*\n\n"
            "• *Lentor MRT Station (TE5):* Seamless sheltered access via Exit 1 to B1/L1.\n\n"
            "⏱️ *First & Last Train Timings:*\n"
            "• *Northbound (Towards Woodlands North TE1 / RTS Link):*\n"
            "  First Train: Mon–Sat `05:58` | Sun/PH `06:18`\n"
            "  Last Train: `00:27` (to Woodlands N), `00:44` (terminating at Woodlands TE2)\n"
            "• *Southbound (Towards Bayshore TE29 / Marina Bay TE20):*\n"
            "  First Train: Mon–Sat `05:52` | Sun/PH `06:12`\n"
            "  Last Train: `23:49` (to Bayshore), `00:05` (to Outram Park), `00:15` (to Caldecott)\n\n"
            "🚌 *Buses at Exit 1 (Bus Stop 55341):*\n"
            "• *Bus 825:* Feeder loop to Yio Chu Kang MRT & AMK 628 Market\n"
            "• *Bus 855:* Direct to Upper Thomson cafe stretch & HarbourFront\n"
            "• *Bus 852:* Direct to SIM / Ngee Ann Poly & Bukit Batok"
        )
    elif action == "menu_mall":
        text = (
            "🏬 *Lentor Modern Mall Highlights:*\n\n"
            "• 🛒 *CS Fresh Supermarket:* Basement 1 (#B1-11 to 16) | 08:00 – 22:00 daily\n"
            "• 👶 *ChildFirst Childcare:* Level 2 (#02-01)\n"
            "• 🏷️ *Resident Discounts (31 Merchants):* Flash your Resident Access Card for 5%–15% off at Burger King, KFC, Ajumma's, QB Premium, Tim Hortons, etc.\n"
            "• 🎟️ *GuocoLand e-Vouchers:* Accepted at 11 participating outlets\n"
            "• 📲 *ResiQ Digital Portal:* Queue for QB Premium or order food online at [resiq-lm.vercel.app](https://resiq-lm.vercel.app/)\n"
            "• 🅿️ *Mall Carpark:* 10-min grace period; EV charging at B1 Lots 39–42"
        )
    elif action == "menu_reno":
        text = (
            "🔨 *Moving In & Renovation Rules:*\n\n"
            "• ⏰ *Working Hours:* Mon–Fri 9am–5pm, Sat 9am–1pm\n"
            "  _STRICTLY NO noisy works on Sundays & Public Holidays._\n"
            "• 💰 *Security Deposit:* S$1,000 (non-hacking) / S$2,000 (hacking)\n"
            "• 🚚 *Residential Loading Bay:* Accessible via Lentor Central ramp (Height limit: 3.8m)\n"
            "• 🛗 *Lift Padding:* Must book with Estate Office 3 days prior ($300 penalty if unpadded)\n"
            "• 🎨 *Official Balcony Paint:* Dulux Thick Smoke (`96YR 09/033`)\n"
            "• 🎨 *Official Interior Paint:* Intermatt BS E55 (White)"
        )
    elif action == "menu_iplus":
        text = (
            "📱 *iPlus Living App & Intercom Setup:*\n\n"
            "1. *Download App:* Search 'iPlus Living' on Apple App Store / Google Play Store.\n"
            "2. *Account Activation:* Register with your email and Property Activation Code (found in your CBRE Welcome Letter).\n"
            "3. *Smart Intercom Buzzer:* Link your mobile under 'Visitor Access'. When guests or delivery riders dial your unit at lobby intercoms, your phone video rings — tap 'Unlock' to open the lobby glass door remotely!\n"
            "4. *Facility Bookings:* Book BBQ, Tennis, Function Room 14–30 days in advance (1 peak session/week per unit, $100–$200 deposit).\n"
            "5. *Support:* Email `managementoffice@LT-MODERN.COM` or call `+65 6054 3370`."
        )
    else:
        text = "Please select an option from the menu."

    await query.edit_message_text(
        text=text,
        reply_markup=back_markup,
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles /help command."""
    if not update.message:
        return

    help_text = (
        "🤖 *Lentor Modern Concierge Commands:*\n\n"
        "• Just message me directly with any question about estate rules, facilities, or mall shops.\n"
        "• `/menu` — Open 1-tap interactive resident quick actions.\n"
        "• `/tip <topic> <advice>` — Submit a community tip for admin review.\n"
        "• `/feedback <suggestion>` — Send feature ideas or feedback directly to project creator & admin @jamesjjboh.\n"
        "• `/bug <issue>` — Report an inaccurate answer or technical bug.\n"
        "• `/help` — View this assistance message.\n\n"
        "*Admin Commands:*\n"
        "• `/reply <user_id> <message>` — Send direct message to a resident.\n"
        "• `/broadcast <message>` — Send estate broadcast to registered residents.\n"
        "• `/admin_stats` — View resident activity, feedback, and content gaps."
    )
    await update.message.reply_text(
        help_text,
        reply_markup=get_quick_menu_keyboard(),
        parse_mode="Markdown",
    )


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
        "Your suggestion has been delivered directly to the project creator & admin (@jamesjjboh). "
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
        "Your report has been dispatched directly to project creator & admin @jamesjjboh to investigate and patch.",
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
                        f"📩 *Message from Project Creator & Admin (@jamesjjboh):*\n\n"
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
    app.add_handler(CommandHandler("menu", menu_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("tip", tip_command))
    app.add_handler(CommandHandler("feedback", feedback_command))
    app.add_handler(CommandHandler("bug", bug_command))
    app.add_handler(CommandHandler("reply", handle_reply_command))
    app.add_handler(CommandHandler("broadcast", handle_broadcast_command))
    app.add_handler(CommandHandler("admin_stats", handle_admin_stats_command))

    # Callback handler for resident interactive 1-tap quick action menu
    app.add_handler(CallbackQueryHandler(handle_quick_menu_callback, pattern=r"^menu_"))

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
