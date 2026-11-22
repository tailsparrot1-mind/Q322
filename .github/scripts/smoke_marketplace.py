from pathlib import Path
from types import SimpleNamespace
import sys
import tkinter as tk

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageGrab

from vkus import cloud_marketplace


class SmokeMarketplaceClient:
    authenticated = False

    def __init__(self):
        self.is_authenticated = self.authenticated
        self.session_persistence_available = True
        self.session = (SimpleNamespace(user={
            "id": "smoke-user",
            "email": "smoke@example.invalid",
            "user_metadata": {"marketplace_role": "Соискатель"},
        }) if self.is_authenticated else None)

    def list_listings(self, search="", kind="Все типы",
                      category="Все категории", city="", **_kwargs):
        fixtures = [{
            "id": "smoke-listing-1",
            "kind": "Ищу",
            "category": "Услуги",
            "title": "Тестовая заявка: нужен мастер",
            "description": "Демонстрационная запись только для UI smoke test.",
            "city": "Оренбург",
            "price": "5000",
            "currency": "RUB",
            "status": "Активно",
            "created_at": "2026-11-22T12:00:00",
            "contact": "smoke@example.invalid",
            "owner_id": "other-user",
        }]
        if search:
            term = search.casefold()
            fixtures = [row for row in fixtures
                        if term in row["title"].casefold()
                        or term in row["description"].casefold()
                        or term in row["city"].casefold()]
        if kind != "Все типы":
            fixtures = [row for row in fixtures if row["kind"] == kind]
        if category != "Все категории":
            fixtures = [row for row in fixtures if row["category"] == category]
        if city:
            fixtures = [row for row in fixtures
                        if city.casefold() in row["city"].casefold()]
        return fixtures


cloud_marketplace.SupabaseMarketplaceClient = SmokeMarketplaceClient

from vkus.app import VkusApp

out = Path("artifacts")
out.mkdir(exist_ok=True)


def size_and_capture(app, width, height, filename):
    app.root.geometry(f"{width}x{height}+0+0")
    app.root.update_idletasks()
    app.root.update()
    actual = (app.root.winfo_width(), app.root.winfo_height())
    assert actual == (width, height), (
        f"Requested {width}x{height}, got {actual[0]}x{actual[1]}"
    )
    x, y = app.root.winfo_rootx(), app.root.winfo_rooty()
    ImageGrab.grab(bbox=(x, y, x + width, y + height)).save(out / filename)

# Unauthenticated role gate and transparent click targets.
app = VkusApp()
app.root.geometry("1920x1080+0+0")
app._unlock()
app._show_marketplace()
app.root.update_idletasks()
app.root.update()
size_and_capture(app, 1920, 1080, "vkus-marketplace-role-gate.png")

page = app.marketplace_page
canvas = page._marketplace_gate_canvas
canvas.update_idletasks()
gate = canvas.master
source = Image.open(ROOT / "vkus" / "assets" / "marketplace_role_gate.png")
cw, ch = canvas.winfo_width(), canvas.winfo_height()
scale = min(cw / source.width, ch / source.height)
ox = (cw - source.width * scale) / 2
oy = (ch - source.height * scale) / 2
hit_x = round(((276 + 772) / 2) * scale + ox)
hit_y = round(((617 + 709) / 2) * scale + oy)
canvas.event_generate("<Button-1>", x=hit_x, y=hit_y)
app.root.update_idletasks()
app.root.update()
forms = [child for child in gate.winfo_children()
         if child is not canvas and child.winfo_exists()]
assert forms, "Role image hotspot did not open the registration form"
size_and_capture(app, 1920, 1080, "vkus-marketplace-registration-form.png")
app.close()

# Authenticated board state with an explicitly synthetic fixture.
SmokeMarketplaceClient.authenticated = True
app = VkusApp()
app.root.geometry("1920x1080+0+0")
app._unlock()
app._show_marketplace()
app.root.update_idletasks()
app.root.update()
page = app.marketplace_page
assert not page._marketplace_gate.winfo_ismapped(), "Authenticated user should see the board"
cards = page._marketplace_cards_frame
assert len(cards.winfo_children()) == 1, "Expected one smoke fixture card"
size_and_capture(app, 1920, 1080, "vkus-marketplace-board-1920x1080.png")

# Compact desktop layout: controls must stay inside the filter panel.
app.root.geometry("1366x768+0+0")
app.root.update_idletasks()
app.root.update()
reset = page._marketplace_reset_button
panel = page._marketplace_filters_panel
assert reset.winfo_ismapped(), "Reset action must remain visible at 1366x768"
reset_right = reset.winfo_rootx() + reset.winfo_width()
panel_right = panel.winfo_rootx() + panel.winfo_width()
assert reset_right <= panel_right, (
    f"Reset button clipped by filter panel: right={reset_right}, panel_right={panel_right}"
)
size_and_capture(app, 1366, 768, "vkus-marketplace-board-1366x768.png")
visible_cards = [child for child in cards.winfo_children()
                 if child.winfo_manager() == "grid"]
assert visible_cards, "A matching listing card must remain visible at 1366x768"
assert visible_cards[0].winfo_width() >= 180, (
    f"Marketplace card is too narrow after resize: {visible_cards[0].winfo_width()}px"
)
actions = page._marketplace_actions_frame
actions_bottom = actions.winfo_rooty() + actions.winfo_height()
root_bottom = app.root.winfo_rooty() + app.root.winfo_height()
assert actions.winfo_height() > 0 and actions_bottom <= root_bottom, (
    f"Marketplace action row is clipped: bottom={actions_bottom}, root_bottom={root_bottom}"
)

search = page._marketplace_search_entry
search.insert(0, "no-such-listing")
search.event_generate("<Return>")
app.root.update_idletasks()
app.root.update()
assert len(cards.winfo_children()) == 1, "No-results state should replace the card"
empty_text = " ".join(
    widget.cget("text") for widget in cards.winfo_children()[0].winfo_children()
    if isinstance(widget, tk.Label)
)
assert "ЗДЕСЬ ПОЯВЯТСЯ ОБЪЯВЛЕНИЯ" in empty_text, (
    "No-results state should display its explanatory heading"
)
reset.invoke()
app.root.update_idletasks()
app.root.update()
assert len(cards.winfo_children()) == 1, "Reset action should restore the listing"
def collect_text(widget):
    values = []
    if isinstance(widget, tk.Label):
        values.append(widget.cget("text"))
    for child in widget.winfo_children():
        values.extend(collect_text(child))
    return values
assert any("Тестовая заявка: нужен мастер" in value
           for value in collect_text(cards)), (
    "Reset must reload and display the matching listing, not only clear fields"
)
search.insert(0, "мастер")
search.event_generate("<Return>")
app.root.update_idletasks()
app.root.update()
assert any("Тестовая заявка: нужен мастер" in value
           for value in collect_text(cards)), "Matching search should restore the card"

def find_button(widget, caption):
    if isinstance(widget, tk.Button) and widget.cget("text") == caption:
        return widget
    for child in widget.winfo_children():
        found = find_button(child, caption)
        if found:
            return found
    return None

work_chip = find_button(page, "Работа")
assert work_chip is not None, "Marketplace category chips must be present"
work_chip.invoke()
app.root.update_idletasks()
app.root.update()
assert "ЗДЕСЬ ПОЯВЯТСЯ ОБЪЯВЛЕНИЯ" in " ".join(collect_text(cards)), (
    "Category chip must filter the listing collection"
)
reset.invoke()
app.root.update_idletasks()
app.root.update()
assert any("Тестовая заявка: нужен мастер" in value
           for value in collect_text(cards)), (
    "Reset must clear category and restore the listing"
)
assert work_chip.cget("bg") == "#101f49", (
    "The selected category chip state should reset visually"
)
app.close()
print("Marketplace role gate, registration, responsive layouts, board card and search/reset smoke tests passed.")
