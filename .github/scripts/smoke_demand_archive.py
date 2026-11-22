from pathlib import Path
import sys
import tempfile
import tkinter.messagebox as messagebox

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from PIL import ImageGrab
from vkus.app import VkusApp
from vkus.demand_store import DemandStore


def main():
    app = VkusApp()
    temp_dir = tempfile.TemporaryDirectory()
    try:
        app._unlock()
        store = DemandStore(Path(temp_dir.name) / "smoke-demand.sqlite3")
        store.save_search_results(
            query="ищу электрика", region="Оренбургская область", city="Орск",
            mode="posts",
            results=[
                {"text": "Ищу электрика для ремонта квартиры", "kind": "post",
                 "url": "https://vk.ru/wall-100_1", "author_name": "Тестовый автор",
                 "profile_url": "https://vk.ru/id100", "city": "Орск",
                 "date_text": "Сегодня"},
                {"comment_text": "Предлагаю услуги электрика", "kind": "comment",
                 "url": "https://vk.ru/wall-200_2", "author_name": "Второй автор",
                 "profile_url": "https://vk.ru/id200", "city": "Орск",
                 "date_text": "Вчера"},
            ],
        )
        app.archive_store = store
        app._open_local_demand_archive()
        app.root.update_idletasks()
        app.root.update()
        assert len(app.archive_tree.get_children()) == 2, "Archive list did not show both records"
        assert len(app.archive_history_tree.get_children()) == 1, "Search history did not show one run"

        app.archive_query_var.set("Предлагаю")
        app._refresh_local_archive()
        app.root.update()
        assert len(app.archive_tree.get_children()) == 1, "Text filter did not narrow archive"

        app.archive_query_var.set("")
        app.archive_city_var.set("Орск")
        app.archive_kind_var.set("post")
        app._refresh_local_archive()
        app.root.update()
        assert len(app.archive_tree.get_children()) == 1, "City/type filters did not work"

        run_id = app.archive_history_tree.get_children()[0]
        app.archive_history_tree.selection_set(run_id)
        app._show_selected_archive_run()
        app.root.update()
        assert len(app.archive_tree.get_children()) == 2, "Search history did not restore its results"

        selected = app.archive_tree.get_children()[0]
        app.archive_tree.selection_set(selected)
        messagebox.askyesno = lambda *_args, **_kwargs: True
        app._delete_selected_archive_record()
        app.root.update()
        assert store.count_items() == 1, "Delete action did not remove the selected record"

        output = Path("artifacts")
        output.mkdir(exist_ok=True)
        ImageGrab.grab().save(output / "vkus-personal-archive-window.png")
        print("Personal archive UI smoke passed: list, filters, search history, delete.")
    finally:
        app.close()
        temp_dir.cleanup()


if __name__ == "__main__":
    main()
