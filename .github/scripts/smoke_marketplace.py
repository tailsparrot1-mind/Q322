from pathlib import Path
import json
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from PIL import ImageGrab
from types import SimpleNamespace
from vkus import cloud_marketplace


class SmokeMarketplaceClient:
    def __init__(self):
        self.session = None
        self.session_persistence_available = True
        self.rows = [{
            "id": "smoke-listing-1",
            "owner_id": "other-user",
            "kind": "Ищу",
            "category": "Услуги",
            "title": "Нужен мастер для ремонта квартиры",
            "description": "Демонстрационная заявка на отделку и мелкий ремонт.",
            "city": "Оренбург",
            "price": 5000,
            "currency": "RUB",
            "status": "Активно",
            "created_at": "2026-11-23T00:00:00",
            "contact": "smoke@example.invalid",
        }]

    @property
    def is_authenticated(self):
        return self.session is not None

    def list_listings(self, *, search="", kind="Все типы",
                      category="Все категории", city="", limit=100, offset=0):
        rows = list(self.rows)
        if search:
            term = search.casefold()
            rows = [r for r in rows if term in (
                r["title"] + " " + r["description"] + " " + r["city"]
            ).casefold()]
        if kind != "Все типы":
            rows = [r for r in rows if r["kind"] == kind]
        if category != "Все категории":
            rows = [r for r in rows if r["category"] == category]
        if city:
            rows = [r for r in rows if city.casefold() in r["city"].casefold()]
        return rows[offset:offset + limit]

    def sign_in(self, email, password):
        if not email or len(password) < 8:
            raise ValueError("Некорректные тестовые данные")
        self.session = SimpleNamespace(user={
            "id": "smoke-user", "email": email,
            "user_metadata": {"marketplace_role": ""},
        })

    def sign_up(self, email, password, role=None):
        self.sign_in(email, password)
        self.set_marketplace_role(role)

    def set_marketplace_role(self, role):
        self.session.user.setdefault("user_metadata", {})["marketplace_role"] = role

    def sign_out(self):
        self.session = None

    def create_listing(self, payload):
        row = dict(payload, id="smoke-created", owner_id="smoke-user",
                   status="Активно", created_at="2026-11-23T00:00:00")
        self.rows.insert(0, row)
        return row

    def update_listing(self, listing_id, payload):
        row = next(r for r in self.rows if str(r["id"]) == str(listing_id))
        row.update(payload)
        return row

    def delete_listing(self, listing_id):
        self.rows = [r for r in self.rows if str(r["id"]) != str(listing_id)]

    def respond_to_listing(self, listing_id, message):
        return {"id": "smoke-response"}

    def get_my_profile(self):
        return {"display_name": "Smoke User", "city": "Оренбург"}

    def save_my_profile(self, display_name, city=""):
        return {"display_name": display_name, "city": city}

    def list_incoming_responses(self, limit=100):
        return []

    def update_response_status(self, response_id, status):
        return {"id": response_id, "status": status}


cloud_marketplace.SupabaseMarketplaceClient = SmokeMarketplaceClient

from vkus.app import VkusApp

out = Path("artifacts")
out.mkdir(exist_ok=True)


def pump(root, seconds=0.08):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        root.update()
        time.sleep(0.01)


def capture(app, filename):
    app.root.update_idletasks()
    app.root.update()
    x, y = app.root.winfo_rootx(), app.root.winfo_rooty()
    w, h = app.root.winfo_width(), app.root.winfo_height()
    ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(out / filename)


def js(web, root, expression, timeout=15):
    result = {}
    errors = []
    web.eval_js_with_callback(
        expression,
        lambda value: result.setdefault("value", value),
        on_error=lambda exc: errors.append(str(exc)),
    )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and "value" not in result and not errors:
        pump(root, 0.05)
    if errors:
        raise AssertionError("WebView JS evaluation failed: " + errors[0])
    if "value" not in result:
        raise AssertionError("Timed out waiting for WebView JavaScript result: " + expression)
    value = result["value"]
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


app = VkusApp()
try:
    app.root.geometry("1920x1080+0+0")
    app._unlock()
    app._show_marketplace()
    pump(app.root, 1.0)
    page = app.marketplace_page
    web = page._marketplace_webview

    ready = js(web, app.root, "document.readyState")
    # WebKitGTK may report "interactive" while the local app:// document is
    # already parsed and its deferred JS is still finishing. The actual
    # readiness gate below is the role-gate DOM becoming visible and usable.
    assert ready in ("interactive", "complete"), (
        f"Marketplace HTML document did not become interactive: {ready!r}"
    )
    deadline = time.monotonic() + 10
    gate_visible = False
    while time.monotonic() < deadline:
        gate_visible = js(web, app.root,
            "!document.getElementById('roleGate').classList.contains('hidden')")
        if gate_visible:
            break
        pump(app.root, 0.1)
    assert gate_visible is True, "Unauthenticated user should see the role gate"
    capture(app, "vkus-marketplace-role-gate.png")

    js(web, app.root,
       "document.querySelector('[data-role=\\\"Соискатель\\\"]').click(); 'ok'")
    auth_visible = js(web, app.root,
        "!document.getElementById('authModal').classList.contains('hidden')")
    assert auth_visible is True, "Role selection should open the login/registration form"
    capture(app, "vkus-marketplace-auth-form.png")

    js(web, app.root, """
      document.getElementById('authEmail').value='smoke@example.invalid';
      document.getElementById('authPassword').value='long-password';
      document.getElementById('authSubmit').click();
      'submitted'
    """)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        count = js(web, app.root, "document.querySelectorAll('.listing-card').length")
        if count == 1:
            break
        pump(app.root, 0.1)
    assert count == 1, f"Expected one real DOM listing card after login, got {count!r}"
    gate_hidden = js(web, app.root,
        "document.getElementById('roleGate').classList.contains('hidden')")
    assert gate_hidden is True, "Successful login should dismiss the role gate"
    capture(app, "vkus-marketplace-board-1920x1080.png")

    js(web, app.root, """
      document.getElementById('filterSearch').value='no-such-listing';
      document.getElementById('applyFilters').click();
      'search'
    """)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        empty = js(web, app.root, "!!document.querySelector('.empty-state')")
        if empty:
            break
        pump(app.root, 0.1)
    assert empty is True, "Search should display a real HTML empty state"

    js(web, app.root, "document.getElementById('resetFilters').click(); 'reset'")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        count = js(web, app.root, "document.querySelectorAll('.listing-card').length")
        if count == 1:
            break
        pump(app.root, 0.1)
    assert count == 1, "Reset should restore the matching listing"

    js(web, app.root,
       "document.querySelector('[data-category=\\\"Работа\\\"]').click(); 'category'")
    selected = js(web, app.root,
        "document.querySelector('[data-category=\\\"Работа\\\"]').classList.contains('active')")
    assert selected is True, "Category chip should show its active state"
    js(web, app.root, "document.getElementById('resetFilters').click(); 'reset'")
    reset_category = js(web, app.root,
        "document.querySelector('[data-category=\\\"Все категории\\\"]').classList.contains('active')")
    assert reset_category is True, "Reset should restore the all-categories chip"

    app.root.geometry("1366x768+0+0")
    pump(app.root, 0.5)
    card_count = js(web, app.root, "document.querySelectorAll('.listing-card').length")
    assert card_count == 1, "Listing card should remain visible at compact desktop size"
    grid_columns = js(web, app.root,
        "getComputedStyle(document.getElementById('listingGrid')).gridTemplateColumns")
    assert grid_columns, "Responsive CSS grid should be active"
    capture(app, "vkus-marketplace-board-1366x768.png")

    report = {
        "result": "PASS",
        "renderer": "tkwry WebView / local HTML CSS JS",
        "tests": [
            "HTML document loaded inside real VkusApp",
            "role gate displayed for unauthenticated user",
            "role selection opened HTML auth form",
            "RPC login authenticated the test user",
            "listing data rendered as HTML cards",
            "search produced empty state",
            "reset restored the listing",
            "category chip active state and reset",
            "responsive layout at 1920x1080 and 1366x768",
        ],
        "screenshots": [
            "vkus-marketplace-role-gate.png",
            "vkus-marketplace-auth-form.png",
            "vkus-marketplace-board-1920x1080.png",
            "vkus-marketplace-board-1366x768.png",
        ],
    }
    (out / "vkus-marketplace-webview-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("PASS: Vkus Marketplace rendered and interacted inside the embedded WebView.")
finally:
    app.close()
