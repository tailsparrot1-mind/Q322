import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "vkus" / "demand_store.py"
SPEC = importlib.util.spec_from_file_location("vkus_demand_store_test_module", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
DemandStore = MODULE.DemandStore


class DemandStoreTests(unittest.TestCase):
    def test_saves_and_deduplicates_within_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DemandStore(Path(tmp) / "one.sqlite3")
            first = {
                "text": "Ищу мастера для ремонта кухни",
                "kind": "post",
                "url": "https://vk.ru/wall-10_20",
                "author_name": "Иван",
                "city": "Орск",
            }
            self.assertEqual(
                store.save_search_results(
                    query="ремонт кухни", region="Оренбургская область",
                    city="Орск", mode="posts", results=[first],
                ),
                1,
            )
            self.assertEqual(
                store.save_search_results(
                    query="ищу мастера", region="Оренбургская область",
                    city="Орск", mode="posts", results=[first, first],
                ),
                1,
            )
            self.assertEqual(store.count_items(), 1)
            recent = store.list_recent()
            self.assertEqual(len(recent), 1)
            self.assertEqual(recent[0]["author_name"], "Иван")
            self.assertEqual(recent[0]["source_url"], "https://vk.ru/wall-10_20")

    def test_workspaces_are_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            one = DemandStore(Path(tmp) / "one.sqlite3")
            two = DemandStore(Path(tmp) / "two.sqlite3")
            item = {"text": "Нужен электрик", "url": "https://vk.ru/wall-1_2"}
            one.save_search_results(
                query="электрик", region="", city="", mode="posts", results=[item]
            )
            self.assertEqual(one.count_items(), 1)
            self.assertEqual(two.count_items(), 0)
            self.assertNotEqual(one.workspace_id, two.workspace_id)

    def test_empty_results_create_search_run_but_no_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DemandStore(Path(tmp) / "empty.sqlite3")
            self.assertEqual(
                store.save_search_results(
                    query="пусто", region="", city="", mode="posts", results=[]
                ),
                0,
            )
            self.assertEqual(store.count_items(), 0)

    def test_workspace_id_survives_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "persistent.sqlite3"
            first = DemandStore(path)
            workspace_id = first.workspace_id
            first.save_search_results(
                query="ремонт", region="", city="", mode="posts",
                results=[{"text": "Ищу мастера", "url": "https://vk.ru/wall-3_4"}],
            )
            reopened = DemandStore(path)
            self.assertEqual(reopened.workspace_id, workspace_id)
            self.assertEqual(reopened.count_items(), 1)

    def test_filters_search_runs_and_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = DemandStore(Path(tmp) / "filters.sqlite3")
            first = {"text": "Ищу электрика для квартиры", "kind": "post",
                     "url": "https://vk.ru/wall-1_1", "author_name": "Алексей", "city": "Орск"}
            second = {"comment_text": "Предлагаю услуги сантехника", "kind": "comment",
                      "url": "https://vk.ru/wall-2_2", "author_name": "Мария", "city": "Оренбург"}
            store.save_search_results(query="электрик", region="", city="Орск",
                                      mode="posts", results=[first])
            store.save_search_results(query="сантехник", region="", city="Оренбург",
                                      mode="comments", results=[second])
            self.assertEqual(store.count_filtered(query="электрик"), 1)
            self.assertEqual(store.count_filtered(kind="comment"), 1)
            self.assertEqual(store.list_items(kind="post")[0]["kind"], "post")
            self.assertEqual(store.list_items(kind="comment")[0]["kind"], "comment")
            self.assertEqual(store.count_filtered(city="Орск"), 1)
            runs = store.list_search_runs()
            self.assertEqual(len(runs), 2)
            run_items = store.list_items(run_id=runs[0]["run_id"])
            self.assertEqual(len(run_items), 1)
            self.assertEqual(run_items[0]["body"], "Предлагаю услуги сантехника")
            self.assertTrue(store.delete_item(run_items[0]["item_id"]))
            self.assertEqual(store.count_items(), 1)
            self.assertFalse(store.delete_item(run_items[0]["item_id"]))


if __name__ == "__main__":
    unittest.main()
