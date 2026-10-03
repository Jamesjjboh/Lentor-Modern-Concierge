"""Admin moderation callback handlers, broadcast engine, and analytics for Lentor Modern Concierge."""

import asyncio
import logging
from typing import Optional

from telegram import ForceReply, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from src import analytics
from src.config import ADMIN_TELEGRAM_ID
from src.database import db_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    """Verifies whether the given Telegram user ID matches the configured admin ID."""
    if not ADMIN_TELEGRAM_ID:
        return False
    return user_id == ADMIN_TELEGRAM_ID


async def notify_admin_new_tip(
    context: ContextTypes.DEFAULT_TYPE,
    tip_id: str,
    topic: str,
    content: str,
    photo_bytes: Optional[bytes] = None,
):
    """Pushes an interactive moderation alert directly to the Admin's private Telegram DM."""
    if not ADMIN_TELEGRAM_ID:
        logger.warning("ADMIN_TELEGRAM_ID not set; skipping admin tip notification.")
        return

    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"mod_approve:{tip_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"mod_reject:{tip_id}"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    message_text = (
        f"🔔 *New Resident Tip Submitted:*\n\n"
        f"🏷️ *Topic:* {topic.capitalize()}\n"
        f"💬 *Tip:* \"{content}\"\n\n"
        f"Approve to make it immediately visible to all ~605 households."
    )

    try:
        if photo_bytes:
            await context.bot.send_photo(
                chat_id=ADMIN_TELEGRAM_ID,
                photo=photo_bytes,
                caption=message_text,
                reply_markup=reply_markup,
                parse_mode="Markdown",
            )
        else:
            await context.bot.send_message(
                chat_id=ADMIN_TELEGRAM_ID,
                text=message_text,
                reply_markup=reply_markup,
                parse_mode="Markdown",
            )
        logger.info(f"Admin notified for tip: {tip_id} (has_photo={bool(photo_bytes)})")
    except Exception as e:
        logger.error(f"Failed to send admin alert for tip {tip_id}: {e}")


async def handle_moderation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles admin tapping [Approve] or [Reject] on an interactive tip alert."""
    query = update.callback_query
    if not query:
        return

    await query.answer()
    user_id = update.effective_user.id if update.effective_user else 0

    if not is_admin(user_id):
        if query.message and query.message.photo:
            await query.edit_message_caption(caption="⛔ You are not authorized to moderate community tips.")
        else:
            await query.edit_message_text("⛔ You are not authorized to moderate community tips.")
        return

    data = query.data or ""
    action, _, tip_id = data.partition(":")

    original_text = ""
    if query.message:
        original_text = query.message.caption or query.message.text or ""

    is_photo_message = bool(query.message and query.message.photo)

    if action == "mod_approve":
        success = db_client.update_tip_status(tip_id, "approved")
        status_text = (
            f"✅ *Tip Approved & Live!*\n\n{original_text}\n\n"
            f"Status: Live in community tips knowledge base."
        )
        if success:
            if is_photo_message:
                await query.edit_message_caption(caption=status_text, parse_mode="Markdown")
            else:
                await query.edit_message_text(status_text, parse_mode="Markdown")
        else:
            if is_photo_message:
                await query.edit_message_caption(caption="⚠️ Could not find or update this tip.")
            else:
                await query.edit_message_text("⚠️ Could not find or update this tip.")

    elif action == "mod_reject":
        db_client.update_tip_status(tip_id, "rejected")
        status_text = (
            f"❌ *Tip Rejected.*\n\n{original_text}\n\nStatus: Rejected."
        )
        if is_photo_message:
            await query.edit_message_caption(caption=status_text, parse_mode="Markdown")
        else:
            await query.edit_message_text(status_text, parse_mode="Markdown")


async def notify_admin_new_feedback(
    context: ContextTypes.DEFAULT_TYPE,
    feedback_id: str,
    user_id: int,
    username: Optional[str],
    first_name: Optional[str],
    category: str,
    message: str,
    photo_bytes: Optional[bytes] = None,
):
    """Pushes a resident feedback/bug report alert to Admin with swipe-to-reply and tap-to-reply buttons."""
    if not ADMIN_TELEGRAM_ID:
        logger.warning("ADMIN_TELEGRAM_ID not set; skipping admin feedback notification.")
        return

    resident_display = first_name or "Resident"
    if username:
        resident_display += f" (@{username})"

    cat_title = category.replace("_", " ").title()

    alert_text = (
        f"💡 *New Resident Feedback / Bug Report*\n\n"
        f"👤 *From:* {resident_display}\n"
        f"🆔 *User ID:* `{user_id}`\n"
        f"🏷️ *Type:* {cat_title}\n"
        f"📝 *Message:*\n\"{message}\"\n\n"
        f"👉 *Swipe left on this message to reply directly to {first_name or 'Resident'}, or tap [ 💬 Reply ] below.*"
    )

    keyboard = [
        [
            InlineKeyboardButton(f"💬 Reply to {first_name or 'Resident'}", callback_data=f"fb_reply:{user_id}:{feedback_id}"),
            InlineKeyboardButton("📁 Mark Resolved", callback_data=f"fb_resolve:{feedback_id}"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        if photo_bytes:
            sent_msg = await context.bot.send_photo(
                chat_id=ADMIN_TELEGRAM_ID,
                photo=photo_bytes,
                caption=alert_text,
                reply_markup=reply_markup,
                parse_mode="Markdown",
            )
        else:
            sent_msg = await context.bot.send_message(
                chat_id=ADMIN_TELEGRAM_ID,
                text=alert_text,
                reply_markup=reply_markup,
                parse_mode="Markdown",
            )

        # Persist mapping so swipe-to-reply works across Cloud Run serverless restarts
        db_client.save_admin_reply_mapping(
            admin_message_id=sent_msg.message_id,
            user_id=user_id,
            resident_name=first_name or "Resident",
            feedback_id=feedback_id,
        )
        logger.info(f"Admin notified for feedback {feedback_id} from user {user_id}")
    except Exception as e:
        logger.error(f"Failed to send admin alert for feedback {feedback_id}: {e}")


async def handle_feedback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles admin tapping [Reply] or [Mark Resolved] on a resident feedback card."""
    query = update.callback_query
    if not query:
        return

    await query.answer()
    user_id = update.effective_user.id if update.effective_user else 0

    if not is_admin(user_id):
        await query.message.reply_text("⛔ You are not authorized.")
        return

    data = query.data or ""
    action, _, rest = data.partition(":")

    if action == "fb_reply":
        target_uid_str, _, feedback_id = rest.partition(":")
        target_uid = int(target_uid_str) if target_uid_str.isdigit() else 0
        prompt_msg = await context.bot.send_message(
            chat_id=ADMIN_TELEGRAM_ID,
            text=f"✍️ Replying to Resident (ID: `{target_uid}`). Type your reply below and send:",
            reply_markup=ForceReply(selective=True),
        )
        # Also map the prompt message to the user ID
        db_client.save_admin_reply_mapping(
            admin_message_id=prompt_msg.message_id,
            user_id=target_uid,
            resident_name="Resident",
            feedback_id=feedback_id,
        )

    elif action == "fb_resolve":
        feedback_id = rest
        db_client.update_feedback_status(feedback_id, "resolved")
        original_text = ""
        if query.message:
            original_text = query.message.caption or query.message.text or ""
        resolved_text = f"📁 *Feedback Marked as Resolved*\n\n{original_text}"

        if query.message and query.message.photo:
            await query.edit_message_caption(caption=resolved_text, parse_mode="Markdown")
        elif query.message:
            await query.edit_message_text(text=resolved_text, parse_mode="Markdown")



async def handle_broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command `/broadcast <message>` with Telegram-compliant rate-limiting."""
    user = update.effective_user
    if not user or not is_admin(user.id):
        if update.message:
            await update.message.reply_text("⛔ This command is restricted to estate administrators.")
        return

    if not context.args:
        if update.message:
            await update.message.reply_text("Usage: `/broadcast 📢 <Your Announcement>`", parse_mode="Markdown")
        return

    broadcast_text = " ".join(context.args)
    subscribers = db_client.get_broadcast_subscribers()

    if not subscribers:
        if update.message:
            await update.message.reply_text("No opted-in subscribers found.")
        return

    status_msg = None
    if update.message:
        status_msg = await update.message.reply_text(f"Starting broadcast to {len(subscribers)} residents...")

    success_count = 0
    fail_count = 0

    # Telegram limit: ~30 msgs per second to different chats. We use 25/sec (0.04s delay) for safety.
    for sub_id in subscribers:
        try:
            await context.bot.send_message(
                chat_id=sub_id,
                text=f"📢 *Estate Announcement (Lentor Modern Concierge)*\n\n{broadcast_text}",
                parse_mode="Markdown",
            )
            success_count += 1
        except Exception as e:
            logger.warning(f"Failed to deliver broadcast to user {sub_id}: {e}")
            fail_count += 1

        await asyncio.sleep(0.04)

    summary_text = (
        f"✅ *Broadcast Complete*\n\n"
        f"• Successfully delivered: {success_count}\n"
        f"• Failed/Blocked: {fail_count}\n"
        f"• Total recipients: {len(subscribers)}"
    )
    if status_msg:
        await status_msg.edit_text(summary_text, parse_mode="Markdown")


async def handle_reply_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command `/reply <user_id> <message>` to send direct message to resident."""
    user = update.effective_user
    if not user or not is_admin(user.id):
        if update.message:
            await update.message.reply_text("⛔ This command is restricted to estate administrators.")
        return

    if not context.args or len(context.args) < 2:
        if update.message:
            await update.message.reply_text("Usage: `/reply <user_id> <your message>`", parse_mode="Markdown")
        return

    target_id_str = context.args[0]
    reply_text = " ".join(context.args[1:])

    if not target_id_str.isdigit():
        if update.message:
            await update.message.reply_text("Invalid User ID. Must be a numeric Telegram ID.")
        return

    target_id = int(target_id_str)
    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=(
                f"📩 *Message from Concierge Developer (@jamesjjboh):*\n\n"
                f"\"{reply_text}\""
            ),
            parse_mode="Markdown",
        )
        if update.message:
            await update.message.reply_text(f"✅ Delivered message to user `{target_id}`.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Failed to send reply to user {target_id}: {e}")
        if update.message:
            await update.message.reply_text(f"⚠️ Failed to deliver to user `{target_id}`: {e}")


async def handle_admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command `/admin_stats [7|30|all]` showing the text-first analytics dashboard."""
    user = update.effective_user
    if not user or not is_admin(user.id):
        if update.message:
            await update.message.reply_text("⛔ This command is restricted to estate administrators.")
        return

    days: Optional[int] = 7
    if context.args:
        arg = context.args[0].lower().rstrip("d")
        if arg == "all":
            days = None
        elif arg.isdigit() and int(arg) > 0:
            days = int(arg)

    stats = db_client.get_analytics_summary(days=days)
    if update.message:
        await update.message.reply_text(
            analytics.format_dashboard(stats),
            reply_markup=analytics.stats_keyboard(days),
            parse_mode="Markdown",
        )


async def handle_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the admin dashboard inline buttons (7d / 30d / All / Full gap list / Refresh)."""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    user_id = update.effective_user.id if update.effective_user else 0
    if not is_admin(user_id):
        await query.edit_message_text("⛔ This dashboard is restricted to estate administrators.")
        return

    view, days = analytics.parse_stats_callback(query.data or "stats_7")
    stats = db_client.get_analytics_summary(days=days)
    text = analytics.format_gaps(stats) if view == "gaps" else analytics.format_dashboard(stats)
    try:
        await query.edit_message_text(
            text,
            reply_markup=analytics.stats_keyboard(days),
            parse_mode="Markdown",
        )
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            logger.error(f"Failed to update stats dashboard: {e}")
