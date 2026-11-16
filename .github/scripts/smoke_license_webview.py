import json
import re
import time
from pathlib import Path
import tkinter as tk
from urllib.parse import urlparse

from PIL import ImageGrab
from tkwry import WebView
from vkus.license_store import LICENSE_STORE_URL, LICENSE_STORE_USER_AGENT

root = tk.Tk()
root.title("Vkus License Store — in-app WebView verification")
root.geometry("1180x760")
host = tk.Frame(root, bg="#030817")
host.pack(fill="both", expand=True)
root.update_idletasks()

errors = []
page_events = []
web = WebView(
    host,
    url=LICENSE_STORE_URL,
    untrusted=True,
    open_external=False,
    user_agent=LICENSE_STORE_USER_AGENT,
    on_page_load=lambda event, url: page_events.append((getattr(event, "name", str(event)), url)),
)
web.when_failed(errors.append)

def pump_until(predicate, timeout, description):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        root.update()
        if errors:
            raise RuntimeError(f"Embedded WebView creation failed: {errors[0]}")
        if predicate():
            return
        time.sleep(0.05)
    raise RuntimeError(f"Timed out waiting for {description}; page events={page_events}; url={getattr(web, 'url', None)!r}")

pump_until(lambda: bool(web.ready), 30, "native WebView readiness")
pump_until(
    lambda: any("finished" in str(event).lower() and url.startswith(LICENSE_STORE_URL) for event, url in page_events),
    45,
    "published License Store page load",
)

probe = {}
script = """JSON.stringify({
  url: location.href,
  title: document.title,
  readyState: document.readyState,
  text: document.body ? document.body.innerText : ""
})"""
web.eval_js_with_callback(
    script,
    lambda value: probe.setdefault("value", value),
    on_error=lambda exc: probe.setdefault("error", str(exc)),
)
pump_until(lambda: "value" in probe or "error" in probe, 20, "store content inspection")
if "error" in probe:
    raise RuntimeError("Could not inspect published store page: " + probe["error"])

snapshot = json.loads(probe["value"])
actual_url = snapshot.get("url", "")
if urlparse(actual_url).hostname != urlparse(LICENSE_STORE_URL).hostname:
    raise RuntimeError(f"Unexpected WebView destination: {actual_url}")

body = re.sub(r"\s+", " ", (snapshot.get("text") or "").replace("\u00a0", " ")).strip()
required = ("79 900", "174 000", "238 000", "BASE", "STANDARD", "PREMIUM")
missing = [item for item in required if item.casefold() not in body.casefold()]
if missing:
    raise RuntimeError(
        "Published storefront content is incomplete or not rendered; "
        f"missing={missing}; title={snapshot.get('title')!r}; body_excerpt={body[:1200]!r}"
    )
if "log in" in body.casefold() and "continue with google" in body.casefold():
    raise RuntimeError("WebView opened the Lovable editor/login page instead of the public storefront")

out = Path("artifacts")
out.mkdir(exist_ok=True)
ImageGrab.grab().save(out / "vkus-license-store-in-app-hero.png")
web.eval_js("document.getElementById('pricing')?.scrollIntoView({block: 'start', behavior: 'instant'});")
end = time.monotonic() + 1.5
while time.monotonic() < end:
    root.update()
    time.sleep(0.05)
ImageGrab.grab().save(out / "vkus-license-store-in-app-pricing.png")

report = {
    "result": "PASS",
    "destination": actual_url,
    "title": snapshot.get("title"),
    "document_ready_state": snapshot.get("readyState"),
    "required_store_content": list(required),
    "page_load_events": [{"event": event, "url": url} for event, url in page_events],
    "screenshot_files": [
        "vkus-license-store-in-app-hero.png",
        "vkus-license-store-in-app-pricing.png",
    ],
}
(out / "vkus-license-store-webview-report.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
)
web.destroy()
root.destroy()
print("Published Vkus License Store loaded inside the Tk host; page URL and all three license prices verified.")
