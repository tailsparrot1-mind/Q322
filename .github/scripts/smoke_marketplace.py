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

    def list_listings(self, search="", **_kwargs):
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
        return fixtures


cloud_marketplace.SupabaseMarketplaceClient = SmokeMarketplaceClient

from vkus.app import VkusApp

out = Path("artifacts")
out.mkdir(exist_ok=True)

# Unauthenticated role gate and transparent click targets.
app = VkusApp()
app.root.geometry("1920x1080+0+0")
app._unlock()
app._show_marketplace()
app.root.update_idletasks()
app.root.update()
ImageGrab.grab().save(out / "vkus-marketplace-role-gate.png")

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
ImageGrab.grab().save(out / "vkus-marketplace-registration-form.png")
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
ImageGrab.grab().save(out / "vkus-marketplace-board-1920x1080.png")

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
ImageGrab.grab().save(out / "vkus-marketplace-board-1366x768.png")

search = page._marketplace_search_entry
search.insert(0, "no-such-listing")
search.event_generate("<Return>")
app.root.update_idletasks()
app.root.update()
assert len(cards.winfo_children()) == 1, "No-results state should replace the card"
reset.invoke()
app.root.update_idletasks()
app.root.update()
assert len(cards.winfo_children()) == 1, "Reset action should restore the listing"
search.insert(0, "мастер")
search.event_generate("<Return>")
app.root.update_idletasks()
app.root.update()
assert len(cards.winfo_children()) == 1, "Matching search should restore the card"
app.close()
print("Marketplace role gate, registration, responsive layouts, board card and search/reset smoke tests passed.")
