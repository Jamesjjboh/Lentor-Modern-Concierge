"""Unit tests for the admin analytics engine (src/analytics.py)."""

import unittest
from datetime import datetime, timedelta, timezone

from src import analytics

NOW = datetime(2026, 10, 3, 9, 0, tzinfo=timezone.utc)


def ts(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


USERS = [
    {"user_id": "1", "first_seen": ts(40), "last_active": ts(1)},
    {"user_id": "2", "first_seen": ts(20), "last_active": ts(10)},
    {"user_id": "3", "first_seen": ts(2), "last_active": ts(0.5)},
    {"user_id": "4", "first_seen": ts(60), "last_active": ts(45)},
]

LOGS = [
    {"timestamp": ts(0.2), "user_query": "Where is the gym?", "tools_called": ["search_bylaws_and_handbook"], "answered_successfully": True},
    {"timestamp": ts(1), "user_query": "Last train to bayshore?", "tools_called": ["search_estate_profile"], "answered_successfully": True},
    {"timestamp": ts(1), "user_query": "Is there a pet salon?", "tools_called": ["search_mall_directory"], "answered_successfully": False},
    {"timestamp": ts(2), "user_query": "is there a pet salon", "tools_called": ["search_mall_directory"], "answered_successfully": False},
    {"timestamp": ts(12), "user_query": "Old unanswered", "tools_called": [], "answered_successfully": False},
    {"timestamp": ts(0.1), "user_query": "[Menu] menu_transit", "tools_called": ["menu_transit"], "answered_successfully": True},
    {"timestamp": ts(0.1), "user_query": "[Menu] menu_transit", "tools_called": ["menu_transit"], "answered_successfully": True},
]

FEEDBACK = [
    {"category": "bug", "status": "new", "created_at": ts(5)},
    {"category": "data_correction", "status": "replied", "created_at": ts(3)},
    {"category": "bug", "status": "new", "created_at": ts(1)},
]


class TestAnalytics(unittest.TestCase):
    def test_users_are_not_households(self):
        s = analytics.compute_analytics(USERS, LOGS, FEEDBACK, days=7, now=NOW)
        self.assertEqual(s["registered_users"], 4)
        self.assertEqual(s["new_users"], 1)  # only user 3 joined within 7d
        self.assertEqual(s["active_7d"], 2)
        self.assertEqual(s["active_30d"], 3)
        self.assertAlmostEqual(s["adoption_pct"], 4 / 605)
        dash = analytics.format_dashboard(s)
        self.assertIn("not households", dash)
        self.assertNotIn("Registered Households", dash)

    def test_total_queries_excludes_menu_taps_and_respects_window(self):
        s7 = analytics.compute_analytics(USERS, LOGS, FEEDBACK, days=7, now=NOW)
        self.assertEqual(s7["total_queries"], 4)
        s_all = analytics.compute_analytics(USERS, LOGS, FEEDBACK, days=None, now=NOW)
        self.assertEqual(s_all["total_queries"], 5)

    def test_gaps_are_deduped_and_ranked(self):
        s = analytics.compute_analytics(USERS, LOGS, FEEDBACK, days=7, now=NOW)
        self.assertEqual(s["unanswered_ranked"], [("Is there a pet salon?", 2)])
        s_all = analytics.compute_analytics(USERS, LOGS, FEEDBACK, days=None, now=NOW)
        self.assertEqual(s_all["unanswered_count"], 3)
        self.assertEqual(s_all["unanswered_ranked"][0][1], 2)

    def test_answer_rate_and_topics_and_menu(self):
        s = analytics.compute_analytics(USERS, LOGS, FEEDBACK, days=7, now=NOW)
        self.assertAlmostEqual(s["answer_rate"], 0.5)
        topics = dict(s["topic_counts"])
        self.assertEqual(topics["Mall & shops"], 2)
        self.assertEqual(dict(s["menu_counts"]), {"Transit & Buses": 2})

    def test_feedback_breakdown(self):
        s = analytics.compute_analytics(USERS, LOGS, FEEDBACK, days=7, now=NOW)
        self.assertEqual(s["feedback_by_category"], {"bug": 2, "data_correction": 1})
        self.assertEqual(s["feedback_new"], 2)
        self.assertEqual(s["feedback_oldest_unresolved_days"], 5)

    def test_daily_series_has_seven_days(self):
        s = analytics.compute_analytics(USERS, LOGS, FEEDBACK, days=7, now=NOW)
        self.assertEqual(len(s["queries_by_day"]), 7)
        self.assertEqual(sum(c for _, c in s["queries_by_day"]), 4 + 0)  # 12-day-old log excluded

    def test_empty_data_does_not_crash(self):
        s = analytics.compute_analytics([], [], [], days=7, now=NOW)
        self.assertIsNone(s["answer_rate"])
        text = analytics.format_dashboard(s)
        self.assertIn("none in this window", text)
        self.assertIn("n/a", text)

    def test_is_answered_heuristic(self):
        self.assertFalse(analytics.is_answered("I don't have specific information on that yet.", []))
        self.assertFalse(analytics.is_answered("No shops found in Lentor Modern Mall matching 'x'", ["search_mall_directory"]))
        self.assertFalse(analytics.is_answered("", []))
        self.assertTrue(analytics.is_answered("The gym is open 6:00 AM – 10:00 PM daily.", ["search_bylaws_and_handbook"]))

    def test_callback_parsing(self):
        self.assertEqual(analytics.parse_stats_callback("stats_7"), ("dash", 7))
        self.assertEqual(analytics.parse_stats_callback("stats_all"), ("dash", None))
        self.assertEqual(analytics.parse_stats_callback("stats_gaps_30"), ("gaps", 30))
        self.assertEqual(analytics.parse_stats_callback("stats_gaps_all"), ("gaps", None))

    def test_admin_question_intent(self):
        self.assertTrue(analytics.is_analytics_question("What did residents ask most this week?"))
        self.assertTrue(analytics.is_analytics_question("how many users do we have"))
        self.assertFalse(analytics.is_analytics_question("What time does the gym open?"))

    def test_gap_list_escapes_markdown(self):
        s = analytics.compute_analytics(
            USERS,
            [{"timestamp": ts(0.1), "user_query": "is *this* [broken]_?", "tools_called": [], "answered_successfully": False}],
            [],
            days=7,
            now=NOW,
        )
        text = analytics.format_gaps(s)
        self.assertNotIn("*this*", text)

    def test_sparkline_and_bar(self):
        self.assertEqual(analytics.sparkline([0, 0, 0]), "▁▁▁")
        self.assertEqual(len(analytics.sparkline([1, 2, 3, 4, 5, 6, 7])), 7)
        self.assertEqual(analytics.progress_bar(0.5), "█████░░░░░")


if __name__ == "__main__":
    unittest.main()
