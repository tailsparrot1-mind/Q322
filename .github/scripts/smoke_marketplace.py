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
        return []


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

app.close()
print("Marketplace role gate and registration hotspot smoke test passed.")
