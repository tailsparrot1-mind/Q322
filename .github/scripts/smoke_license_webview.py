import json
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
vkus_app_module.messagebox.showerror = lambda title, message, parent=None: errors.append(f"{title}: {message}")

try:
    # Real desktop application; local lock is bypassed only by this CI harness.
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

    def finished():
        return any(
            "finished" in str(event).lower() and url.startswith(LICENSE_STORE_URL)
            for event, url in getattr(app, "license_store_page_events", [])
        )

    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        root.update()
        if errors:
            raise RuntimeError("Vkus Store WebView error: " + errors[0])
        if finished():
            break
        time.sleep(0.05)
    else:
        raise RuntimeError(
            "Published storefront did not finish loading inside Vkus within 60 seconds. "
            f"events={getattr(app, 'license_store_page_events', [])}; "
            f"current_url={getattr(web, 'url', None)!r}"
        )

    state = web.get_state()
    actual_url = getattr(state, "url", None) or getattr(web, "url", "")
    title = getattr(state, "title", "") or ""
    if urlparse(actual_url).hostname != urlparse(LICENSE_STORE_URL).hostname:
        raise RuntimeError(f"Vkus opened an unexpected destination: {actual_url}")
    if "vkus" not in title.casefold():
        raise RuntimeError(f"Published page title is not the Vkus storefront: {title!r}")

    # Let the page finish painting before taking the real application screenshot.
    end = time.monotonic() + 2
    while time.monotonic() < end:
        root.update()
        time.sleep(0.05)

    out = Path("artifacts")
    out.mkdir(exist_ok=True)
    ImageGrab.grab().save(out / "vkus-license-store-in-real-vkus.png")

    report = {
        "result": "PASS",
        "test_scope": "real VkusApp launched under Xvfb; local lock bypassed only by CI harness",
        "destination": actual_url,
        "title": title,
        "page_load_events": [
            {"event": event, "url": url}
            for event, url in app.license_store_page_events
        ],
        "screenshot": "vkus-license-store-in-real-vkus.png",
    }
    (out / "vkus-license-store-webview-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("PASS: the published Vkus License Store rendered inside the real Vkus desktop window.")
finally:
    if app is not None:
        try:
            Path("artifacts").mkdir(exist_ok=True)
            ImageGrab.grab().save(Path("artifacts") / "vkus-license-store-debug.png")
        except Exception:
            pass
        try:
            app.close()
        except Exception:
            try:
                app.root.destroy()
            except Exception:
                pass
