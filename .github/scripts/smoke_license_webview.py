from pathlib import Path
import time
import tkinter as tk

from PIL import ImageGrab
from tkwry import WebView

URL = "https://id-preview--78bbce34-69ac-42ab-9e42-f528ea437805.lovable.app"

root = tk.Tk()
root.title("Vkus Store WebView smoke test")
root.geometry("1180x760")
host = tk.Frame(root, bg="#030817")
host.pack(fill="both", expand=True)
root.update_idletasks()

errors = []
web = WebView(host, url=URL, untrusted=True, open_external=False,
              user_agent="VkusDesktop/3.28")
web.when_failed(errors.append)

deadline = time.monotonic() + 35
while time.monotonic() < deadline and not errors:
    root.update()
    if web.ready:
        break
    time.sleep(0.05)

if errors:
    raise RuntimeError("Embedded WebView creation failed: " + str(errors[0]))
if not web.ready:
    raise RuntimeError("Embedded WebView did not become ready")

# Allow the remote storefront to paint before capturing the actual embedded view.
until = time.monotonic() + 8
while time.monotonic() < until:
    root.update()
    time.sleep(0.05)

out = Path("artifacts")
out.mkdir(exist_ok=True)
ImageGrab.grab().save(out / "vkus-license-store-in-app-webview.png")
web.destroy()
root.destroy()
print("Embedded Vkus Store WebView created and captured inside the Tk host frame.")
