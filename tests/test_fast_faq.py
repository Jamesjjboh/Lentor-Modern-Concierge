"""Unit tests for the Zero-Shot Fast FAQ cache and in-memory data cache."""

import unittest
from src.fast_faq import match_fast_faq
from src.agent import LentorAgent, get_cached_json, _DATA_CACHE


class TestFastFAQ(unittest.TestCase):
    def test_gym_hours_match(self):
        res = match_fast_faq("What time does the gym open?")
        self.assertIsNotNone(res)
        text, tools = res
        self.assertIn("6:00 AM – 10:00 PM daily", text)
        self.assertIn("search_bylaws_and_handbook", tools)

    def test_swimming_pool_match(self):
        res = match_fast_faq("pool opening hours")
        self.assertIsNotNone(res)
        text, tools = res
        self.assertIn("7:00 AM – 10:00 PM daily", text)
        self.assertIn("search_bylaws_and_handbook", tools)

    def test_tennis_court_match(self):
        res = match_fast_faq("how to book tennis court?")
        self.assertIsNotNone(res)
        text, tools = res
        self.assertIn("iPlus Living", text)
        self.assertIn("search_bylaws_and_handbook", tools)

    def test_renovation_hours_match(self):
        res = match_fast_faq("what are the reno hours on saturday?")
        self.assertIsNotNone(res)
        text, tools = res
        self.assertIn("9:00 AM – 1:00 PM", text)
        self.assertIn("search_bylaws_and_handbook", tools)

    def test_first_last_train_timings_match(self):
        res = match_fast_faq("when is the last train to Woodlands?")
        self.assertIsNotNone(res)
        text, tools = res
        self.assertIn("Lentor MRT Station", text)
        self.assertIn("search_estate_profile", tools)

    def test_balcony_paint_code_match(self):
        res = match_fast_faq("what is the balcony paint code?")
        self.assertIsNotNone(res)
        text, tools = res
        self.assertIn("Dulux Thick Smoke", text)
        self.assertIn("96YR 09/033", text)
        self.assertIn("search_bylaws_and_handbook", tools)

    def test_maintenance_fees_match(self):
        res = match_fast_faq("how much are the maintenance fees?")
        self.assertIsNotNone(res)
        text, tools = res
        self.assertIn("44.80/SV base", text)
        self.assertIn("search_estate_profile", tools)

    def test_cs_fresh_match(self):
        res = match_fast_faq("what time does cs fresh close?")
        self.assertIsNotNone(res)
        text, tools = res
        self.assertIn("08:00 – 22:00 daily", text)
        self.assertIn("search_mall_directory", tools)

    def test_primary_schools_proximity_match(self):
        res = match_fast_faq("is anderson primary within 1km?")
        self.assertIsNotNone(res)
        text, tools = res
        self.assertIn("Anderson Primary School", text)
        self.assertIn("strictly the *ONLY* primary school within 1km", text)
        self.assertIn("search_estate_profile", tools)

    def test_developer_specs_match(self):
        res = match_fast_faq("who is the developer of lentor modern?")
        self.assertIsNotNone(res)
        text, tools = res
        self.assertIn("GuocoLand", text)
        self.assertIn("605 units", text)
        self.assertIn("search_estate_profile", tools)

    def test_physical_concierge_desk_hours_match(self):
        res = match_fast_faq("What time is the physical concierge opened until")
        self.assertIsNotNone(res)
        text, tools = res
        self.assertIn("9:00 AM – 8:00 PM daily", text)
        self.assertIn("Security Control", text)
        self.assertIn("search_bylaws_and_handbook", tools)

    def test_dlp_end_date_match(self):
        res = match_fast_faq("when does the defect liability period end")
        self.assertIsNotNone(res)
        text, tools = res
        self.assertIn("12 months from your individual Key Collection", text)
        self.assertIn("Novade", text)
        self.assertIn("search_bylaws_and_handbook", tools)

    def test_security_numbers_match(self):
        res = match_fast_faq("Security numbers")
        self.assertIsNotNone(res)
        text, tools = res
        self.assertIn("+65 6054 3379", text)
        self.assertIn("+65 6054 3370", text)
        self.assertIn("+65 6054 3375", text)
        self.assertIn("+65 6259 0700", text)
        self.assertIn("search_bylaws_and_handbook", tools)

    def test_rubbish_chute_stuck_match(self):
        queries = [
            "rubbish chute is stuck",
            "chute stuck",
            "refuse chute choked",
            "where to throw bulky boxes",
        ]
        for q in queries:
            res = match_fast_faq(q)
            self.assertIsNotNone(res, f"Failed to match Fast FAQ for: {q}")
            text, tools = res
            self.assertIn("Level 2 Bin Area", text)
            self.assertIn("+65 6054 3370", text)
            self.assertIn("+65 6054 3379", text)
            self.assertIn("search_bylaws_and_handbook", tools)

    def test_coworking_and_meeting_room_match(self):
        queries = [
            "coworking space",
            "co-working at lentor modern",
            "is there a meeting room",
            "business lounge",
            "where can i study",
        ]
        for q in queries:
            res = match_fast_faq(q)
            self.assertIsNotNone(res, f"Failed to match Fast FAQ for: {q}")
            text, tools = res
            self.assertIn("Business Lounge", text)
            self.assertIn("6-Person Meeting Room", text)
            self.assertIn("iPlus Living", text)
            self.assertIn("search_bylaws_and_handbook", tools)

    def test_unmatched_query_falls_back(self):
        res = match_fast_faq("Can I keep an exotic lizard in my unit?")
        self.assertIsNone(res)

    def test_boundary_lengths(self):
        self.assertIsNone(match_fast_faq(""))
        self.assertIsNone(match_fast_faq("ab"))
        self.assertIsNone(match_fast_faq("x" * 200))

    def test_agent_run_query_fast_path(self):
        agent = LentorAgent(api_key=None)
        text, tools = agent.run_query("gym hours")
        self.assertIn("6:00 AM – 10:00 PM daily", text)
        self.assertIn("search_bylaws_and_handbook", tools)

    def test_qb_premium_discount_match(self):
        res = match_fast_faq("Is there resident discount for qb premium")
        self.assertIsNotNone(res)
        text, tools = res
        self.assertIn("QB PREMIUM", text)
        self.assertIn("$3 off all haircuts", text)
        self.assertIn("search_mall_directory", tools)

    def test_jew_kit_discount_match(self):
        res = match_fast_faq("Does Jew kit chicken rice have resident discount")
        self.assertIsNotNone(res)
        text, tools = res
        self.assertIn("Jew Kit Hainanese Chicken Rice", text)
        self.assertIn("15% off total bill", text)
        self.assertIn("search_mall_directory", tools)

    def test_kfc_discount_match(self):
        res = match_fast_faq("is there a resident discount for KFC?")
        self.assertIsNotNone(res)
        text, tools = res
        self.assertIn("KFC", text)
        self.assertIn("15% off with minimum spending of $15", text)
        self.assertIn("search_mall_directory", tools)

    def test_tim_hortons_discount_match(self):
        res = match_fast_faq("tim hortons resident promo")
        self.assertIsNotNone(res)
        text, tools = res
        self.assertIn("Tim Hortons", text)
        self.assertIn("15% off with minimum spending of $15", text)
        self.assertIn("search_mall_directory", tools)

    def test_burger_king_discount_match(self):
        res = match_fast_faq("does burger king have resident discount?")
        self.assertIsNotNone(res)
        text, tools = res
        self.assertIn("Burger King", text)
        self.assertIn("10% off total bill", text)
        self.assertIn("search_mall_directory", tools)

    def test_dynamic_store_discount_toast_and_roll(self):
        res = match_fast_faq("any discount for toast & roll?")
        self.assertIsNotNone(res)
        text, tools = res
        self.assertIn("Toast & Roll", text)
        self.assertIn("5% off total bill", text)
        self.assertIn("search_mall_directory", tools)

    def test_dynamic_store_discount_non_discount_store(self):
        res = match_fast_faq("does chagee have resident discount?")
        self.assertIsNotNone(res)
        text, tools = res
        self.assertIn("CHAGEE", text)
        self.assertIn("Does not currently offer a specific resident discount", text)
        self.assertIn("search_mall_directory", tools)

    def test_general_discounts_overview(self):
        res = match_fast_faq("what are the resident discounts?")
        self.assertIsNotNone(res)
        text, tools = res
        self.assertIn("Lentor Modern Resident Discounts & Perks Overview", text)
        self.assertIn("Jew Kit Chicken Rice", text)
        self.assertIn("QB PREMIUM", text)
        self.assertIn("search_mall_directory", tools)

    def test_build_injected_context_mall(self):
        from src.agent import build_injected_context
        context, tools = build_injected_context("Where is Toast & Roll?")
        self.assertIn("Toast & Roll", context)
        self.assertIn("search_mall_directory", tools)

    def test_build_injected_context_bylaws(self):
        from src.agent import build_injected_context
        context, tools = build_injected_context("what are the rules for aircon ledge?")
        self.assertIn("Aircon", context)
        self.assertIn("search_bylaws_and_handbook", tools)

    def test_cached_json_in_memory(self):
        data = get_cached_json("mall_directory.json")
        self.assertIsNotNone(data)
        self.assertIn("mall_directory.json", _DATA_CACHE)
        # Second call returns same cached instance
        data2 = get_cached_json("mall_directory.json")
        self.assertIs(data, data2)


if __name__ == "__main__":
    unittest.main()
