from pathlib import Path
import sys
import tkinter as tk

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageGrab

from vkus import cloud_marketplace


class SmokeMarketplaceClient:
    is_authenticated = False
    session = None
    session_persistence_available = False

    def list_listings(self, **_kwargs):
        return [
            {"id": "smoke-1", "kind": "Ищу", "category": "Услуги",
             "title": "Нужен мастер по ремонту ноутбука",
             "description": "Ищу специалиста для диагностики и ремонта ноутбука. Желательно сегодня.",
             "city": "Оренбург", "price": "3000", "currency": "RUB",
             "status": "Активно", "created_at": "2026-11-20T10:30:00",
             "owner_id": "demo-user", "contact": "@demo"},
            {"id": "smoke-2", "kind": "Предлагаю", "category": "Работа",
             "title": "Настройка рекламы и аналитики",
             "description": "Помогаю настроить рекламные кампании и отслеживать заявки.",
             "city": "Орск", "price": "5000", "currency": "RUB",
             "status": "Активно", "created_at": "2026-11-19T16:15:00",
             "owner_id": "demo-user-2", "contact": "@specialist"},
        ]


cloud_marketplace.SupabaseMarketplaceClient = SmokeMarketplaceClient

from vkus.app import VkusApp

app = VkusApp()
app._unlock()
app._show_marketplace()
app.root.update_idletasks()
app.root.update()

out = Path("artifacts")
out.mkdir(exist_ok=True)
ImageGrab.grab().save(out / "vkus-marketplace-role-gate.png")

canvas = app.marketplace_page._marketplace_gate_canvas
canvas.update_idletasks()
gate = canvas.master
source = Image.open(
    ROOT / "vkus" / "assets" / "marketplace_role_gate.png"
)
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

# Capture the real announcement board: live cards, filters and publication controls.
gate.place_forget()
dashboard = app.marketplace_page
assert dashboard.winfo_exists(), "Marketplace board was not created"
dashboard.lift()
app.root.update_idletasks()
app.root.update()

cards = app.marketplace_page._marketplace_cards_frame
assert cards.winfo_exists(), "Marketplace listing cards container was not created"
assert len(cards.winfo_children()) >= 2, "Marketplace did not render the fixture listings"

search_entry = app.marketplace_page._marketplace_search_entry
assert search_entry.winfo_exists(), "Marketplace search entry was not created"
search_entry.insert(0, "ремонт ноутбука")
search_entry.event_generate("<Return>")
app.root.update_idletasks()
app.root.update()
search_entry.delete(0, tk.END)
app.root.update_idletasks()
app.root.update()

ImageGrab.grab().save(out / "vkus-marketplace-home-running.png")

app.close()
print("Marketplace role gate, registration, dashboard and search smoke test passed.")
