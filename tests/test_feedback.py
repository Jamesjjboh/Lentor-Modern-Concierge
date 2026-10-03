"""Unit tests for resident answer feedback (👍/👎), admin alerts, and flagged query workflows."""

import unittest
from unittest.mock import AsyncMock, MagicMock
from src.database import DatabaseClient
from src.admin import is_admin, notify_admin_flagged_answer, handle_flagged_command
from src.bot import (
    get_answer_feedback_keyboard,
    get_answer_feedback_done_keyboard,
    handle_answer_feedback_callback,
)


class TestFeedbackWorkflow(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Create fresh in-memory db client for isolated testing
        self.db = DatabaseClient(project_id=None)
        self.db._mock_mode = True

    def test_answer_feedback_keyboards(self):
        kb = get_answer_feedback_keyboard("log_123")
        self.assertEqual(len(kb.inline_keyboard), 1)
        self.assertEqual(len(kb.inline_keyboard[0]), 2)
        self.assertIn("Helpful", kb.inline_keyboard[0][0].text)
        self.assertEqual(kb.inline_keyboard[0][0].callback_data, "fb_rate:pos:log_123")
        self.assertIn("Inaccurate", kb.inline_keyboard[0][1].text)
        self.assertEqual(kb.inline_keyboard[0][1].callback_data, "fb_rate:neg:log_123")

        done_pos = get_answer_feedback_done_keyboard("pos")
        self.assertIn("Helpful", done_pos.inline_keyboard[0][0].text)

        done_neg = get_answer_feedback_done_keyboard("neg")
        self.assertIn("Flagged", done_neg.inline_keyboard[0][0].text)

    def test_log_and_update_query_feedback(self):
        log_id = self.db.log_query(
            user_id=12345,
            user_query="What are the gym hours?",
            tools_called=["search_bylaws_and_handbook"],
            agent_response="The gym is open 6:00 AM to 10:00 PM.",
            answered_successfully=True,
        )

        entry = self.db.get_query_log(log_id)
        self.assertIsNotNone(entry)
        self.assertEqual(entry["user_query"], "What are the gym hours?")
        self.assertIsNone(entry.get("feedback"))

        # Update feedback to helpful
        res = self.db.update_query_feedback(log_id, "helpful")
        self.assertTrue(res)
        entry = self.db.get_query_log(log_id)
        self.assertEqual(entry["feedback"], "helpful")

        # Update feedback to inaccurate
        res2 = self.db.update_query_feedback(log_id, "inaccurate")
        self.assertTrue(res2)
        entry = self.db.get_query_log(log_id)
        self.assertEqual(entry["feedback"], "inaccurate")

        # Retrieve flagged queries
        flagged = self.db.get_flagged_queries()
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0]["log_id"], log_id)

    async def test_callback_positive_feedback(self):
        # Mock Telegram callback query update
        from src.database import db_client
        log_id = db_client.log_query(
            user_id=999,
            user_query="Can I book the tennis court?",
            tools_called=[],
            agent_response="Yes, via iPlus Living.",
        )

        update = MagicMock()
        update.callback_query.data = f"fb_rate:pos:{log_id}"
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_reply_markup = AsyncMock()
        update.effective_user.id = 999
        update.effective_user.username = "resident_jane"
        update.effective_user.first_name = "Jane"

        context = MagicMock()

        await handle_answer_feedback_callback(update, context)

        update.callback_query.answer.assert_called_once()
        log_data = db_client.get_query_log(log_id)
        self.assertEqual(log_data["feedback"], "helpful")

    async def test_callback_negative_feedback_triggers_alert(self):
        from src.database import db_client
        log_id = db_client.log_query(
            user_id=888,
            user_query="Where is the swimming pool?",
            tools_called=["search_bylaws_and_handbook"],
            agent_response="Level 4.",
        )

        update = MagicMock()
        update.callback_query.data = f"fb_rate:neg:{log_id}"
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_reply_markup = AsyncMock()
        update.effective_user.id = 888
        update.effective_user.username = "resident_bob"
        update.effective_user.first_name = "Bob"

        context = MagicMock()
        context.bot.send_message = AsyncMock(return_value=MagicMock(message_id=777))

        await handle_answer_feedback_callback(update, context)

        update.callback_query.answer.assert_called_once()
        log_data = db_client.get_query_log(log_id)
        self.assertEqual(log_data["feedback"], "inaccurate")


if __name__ == "__main__":
    unittest.main()
