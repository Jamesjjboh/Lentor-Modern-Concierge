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

    def test_cached_json_in_memory(self):
        data = get_cached_json("mall_directory.json")
        self.assertIsNotNone(data)
        self.assertIn("mall_directory.json", _DATA_CACHE)
        # Second call returns same cached instance
        data2 = get_cached_json("mall_directory.json")
        self.assertIs(data, data2)


if __name__ == "__main__":
    unittest.main()
