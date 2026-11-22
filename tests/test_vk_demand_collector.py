import runpy
import unittest

# Load the standalone module without importing vkus/__init__.py, which pulls
# the full desktop runtime (including Selenium) into this pure unit test.
_collector = runpy.run_path("vkus/vk_demand_collector.py")
classify_intent = _collector["classify_intent"]
normalize_result = _collector["normalize_result"]


class VKDemandCollectorTests(unittest.TestCase):
    def test_clear_request_is_classified(self):
        self.assertEqual(classify_intent("Ищу мастера для ремонта стиральной машины"), ("request", 0.68))

    def test_clear_offer_is_classified(self):
        self.assertEqual(classify_intent("Предлагаю услуги электрика, выполняю работы"), ("offer", 0.68))

    def test_ambiguous_text_stays_unknown(self):
        self.assertEqual(classify_intent("Сегодня обсуждали ремонт квартиры"), ("unknown", 0.0))

    def test_conflicting_signals_stay_unknown(self):
        self.assertEqual(classify_intent("Ищу мастера, сам предлагаю услуги ремонта"), ("unknown", 0.0))

    def test_post_normalization(self):
        record = normalize_result({
            "url": "https://vk.ru/wall-123_456",
            "text": "Ищу мастера для ремонта стиральной машины",
            "kind": "posts",
            "author_name": "Тестовый автор",
            "date_ts": 1795300000000,
        }, city="Орск", region="Оренбургская область")
        self.assertIsNotNone(record)
        self.assertEqual(record["source_kind"], "post")
        self.assertEqual(record["intent"], "request")
        self.assertEqual(record["city"], "Орск")
        self.assertTrue(record["external_key"])
        self.assertTrue(record["published_at"])

    def test_reject_non_vk_url(self):
        self.assertIsNone(normalize_result({
            "url": "https://example.com/post/1",
            "text": "Ищу мастера для ремонта",
            "kind": "posts",
        }))


if __name__ == "__main__":
    unittest.main()
