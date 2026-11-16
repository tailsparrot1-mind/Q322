import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from PIL import ImageGrab

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import vkus.app as vkus_app_module
from vkus.app import VkusApp
from vkus.license_store import LICENSE_STORE_URL


app = None
errors = []
probe = {"pending": False, "value": None, "error": None}
vkus_app_module.messagebox.showerror = lambda title, message, parent=None: errors.append(f"{title}: {message}")

try:
    # Launch the real Vkus desktop application, then unlock only inside this
    # automated test so the smoke test can navigate to the actual store tab.
    app = VkusApp()
    root = app.root
    root.geometry("1180x760")
    root.update_idletasks()
    root.update()
    app._unlock()
    root.update_idletasks()
    root.update()
    app._show_license_store()
    root.update_idletasks()
    root.update()

    web = getattr(app, "license_store_webview", None)
    if web is None:
        raise RuntimeError("Vkus did not create the embedded License Store WebView")

    def probe_page():
        if probe["pending"] or probe["value"] is not None or probe["error"] is not None:
            return
        probe["pending"] = True

        def on_value(value):
            probe["pending"] = False
            probe["value"] = value

        def on_error(exc):
            probe["pending"] = False
            probe["error"] = str(exc)

        web.eval_js_with_callback(
            """JSON.stringify({
              url: location.href,
              title: document.title,
              readyState: document.readyState,
              text: document.body ? document.body.innerText : ""
            })""",
            on_value,
            on_error=on_error,
        )

    deadline = time.monotonic() + 60
    snapshot = None
    while time.monotonic() < deadline:
        root.update()
        if errors:
            raise RuntimeError("Vkus Store WebView error: " + errors[0])
        if web.ready:
            probe_page()
        if probe["error"]:
            raise RuntimeError("Could not inspect storefront in Vkus: " + probe["error"])
        if probe["value"] is not None:
            try:
                candidate = json.loads(probe["value"])
            except Exception:
                candidate = None
            if candidate:
                body_text = (candidate.get("text") or "").replace("\u00a0", " ")
                normalized = re.sub(r"\s+", " ", body_text).strip()
                required = ("79 900", "174 000", "238 000", "BASE", "STANDARD", "PREMIUM")
                missing = [item for item in required if item.casefold() not in normalized.casefold()]
                if not missing:
                    snapshot = candidate
                    break
                # Re-probe while the Lovable SPA is still hydrating/rendering.
                probe["value"] = None
                time.sleep(0.35)
        time.sleep(0.05)

    if snapshot is None:
        last_text = ""
        if probe["value"]:
            try:
                last_text = (json.loads(probe["value"]).get("text") or "")[:1200]
            except Exception:
                last_text = str(probe["value"])[:1200]
        raise RuntimeError(
            "Published License Store did not render all three tariffs inside Vkus "
            f"within 60 seconds. Current WebView URL={getattr(web, 'url', None)!r}; "
            f"page text={last_text!r}"
        )

    actual_url = snapshot.get("url", "")
    if urlparse(actual_url).hostname != urlparse(LICENSE_STORE_URL).hostname:
        raise RuntimeError(f"Vkus opened an unexpected destination: {actual_url}")

    body = re.sub(r"\s+", " ", (snapshot.get("text") or "").replace("\u00a0", " ")).strip()
    if "log in" in body.casefold() and "continue with google" in body.casefold():
        raise RuntimeError("Vkus opened the Lovable editor/login page instead of the public storefront")

    out = Path("artifacts")
    out.mkdir(exist_ok=True)
    ImageGrab.grab().save(out / "vkus-license-store-in-real-vkus-hero.png")
    web.eval_js("document.getElementById('pricing')?.scrollIntoView({block: 'start', behavior: 'instant'});")
    end = time.monotonic() + 1.5
    while time.monotonic() < end:
        root.update()
        time.sleep(0.05)
    ImageGrab.grab().save(out / "vkus-license-store-in-real-vkus-pricing.png")

    report = {
        "result": "PASS",
        "test_scope": "actual VkusApp launched under Xvfb; local lock bypassed only by test harness",
        "destination": actual_url,
        "title": snapshot.get("title"),
        "document_ready_state": snapshot.get("readyState"),
        "required_store_content": ["79 900", "174 000", "238 000", "BASE", "STANDARD", "PREMIUM"],
        "screenshots": [
            "vkus-license-store-in-real-vkus-hero.png",
            "vkus-license-store-in-real-vkus-pricing.png",
        ],
    }
    (out / "vkus-license-store-webview-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("PASS: the published Vkus License Store rendered inside the real Vkus desktop window.")
finally:
    if app is not None:
        try:
            app.close()
        except Exception:
            try:
                app.root.destroy()
            except Exception:
                pass
