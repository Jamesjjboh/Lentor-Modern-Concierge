"""Admin moderation callback handlers, broadcast engine, and analytics for Lentor Modern Concierge."""

import asyncio
import logging
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.config import ADMIN_TELEGRAM_ID
from src.database import db_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def is_admin(user_id: int) -> bool:
    """Verifies whether the given Telegram user ID matches the configured admin ID."""
    if not ADMIN_TELEGRAM_ID:
        return False
    return user_id == ADMIN_TELEGRAM_ID


async def notify_admin_new_tip(context: ContextTypes.DEFAULT_TYPE, tip_id: str, topic: str, content: str):
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
        await context.bot.send_message(
            chat_id=ADMIN_TELEGRAM_ID,
            text=message_text,
            reply_markup=reply_markup,
            parse_mode="Markdown",
        )
        logger.info(f"Admin notified for tip: {tip_id}")
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
        await query.edit_message_text("⛔ You are not authorized to moderate community tips.")
        return

    data = query.data or ""
    action, _, tip_id = data.partition(":")

    if action == "mod_approve":
        success = db_client.update_tip_status(tip_id, "approved")
        if success:
            await query.edit_message_text(
                f"✅ *Tip Approved & Live!*\n\n{query.message.text if query.message else ''}\n\n"
                f"Status: Live in community tips knowledge base.",
                parse_mode="Markdown",
            )
        else:
            await query.edit_message_text("⚠️ Could not find or update this tip.")

    elif action == "mod_reject":
        db_client.update_tip_status(tip_id, "rejected")
        await query.edit_message_text(
            f"❌ *Tip Rejected.*\n\n{query.message.text if query.message else ''}\n\nStatus: Rejected.",
            parse_mode="Markdown",
        )


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


async def handle_admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command `/admin_stats` showing total users, activity, and content gaps."""
    user = update.effective_user
    if not user or not is_admin(user.id):
        if update.message:
            await update.message.reply_text("⛔ This command is restricted to estate administrators.")
        return

    stats = db_client.get_analytics_summary()
    unanswered_lines = ""
    for idx, q in enumerate(stats.get("unanswered_examples", []), start=1):
        unanswered_lines += f"\n  {idx}. \"{q}\""

    if not unanswered_lines:
        unanswered_lines = "\n  (No unanswered queries logged yet 🎉)"

    report = (
        f"📊 *Lentor Modern Concierge Analytics*\n\n"
        f"👥 *Total Registered Households:* {stats.get('total_users', 0)}\n"
        f"💬 *Total Queries Logged:* {stats.get('total_queries', 0)}\n"
        f"❓ *Unanswered Content Gaps ({stats.get('unanswered_count', 0)}):*{unanswered_lines}\n\n"
        f"_Use this report to identify missing bylaws or untracked mall shops._"
    )
    if update.message:
        await update.message.reply_text(report, parse_mode="Markdown")
