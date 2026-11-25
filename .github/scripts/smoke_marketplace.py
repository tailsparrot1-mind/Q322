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
        self.list_error = ""
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
        if self.list_error:
            raise ValueError(self.list_error)
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

    # tkwry's native child WebView must finish Tk layout before JS evaluation.
    # On Linux/WebKitGTK an early eval can remain queued forever while the
    # X11 child surface is still being created, even though Tk itself updates.
    page.update_idletasks()
    page.update()
    web.sync_bounds()
    if not web.wait_until_ready():
        raise AssertionError("Marketplace WebView did not become layout-ready")
    pump(app.root, 0.5)

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

    # Startup bootstrap must complete after the local app:// navigation settles;
    # a cancelled first RPC otherwise leaves a visible "Нет соединения" toast.
    deadline = time.monotonic() + 10
    connection_ready = False
    while time.monotonic() < deadline:
        connection_ready = js(web, app.root,
            "document.getElementById('connectionState').textContent.includes('Общая база Vkus · HTTPS')")
        if connection_ready:
            break
        pump(app.root, 0.1)
    assert connection_ready is True, "Initial Marketplace bootstrap RPC did not complete"
    startup_toast = js(web, app.root, "document.getElementById('toast').textContent.trim()")
    assert not startup_toast, f"Unexpected startup RPC error: {startup_toast}"

    # A handled backend error must not be rendered as a healthy connection.
    client = page._marketplace_client
    client.list_error = "Smoke: simulated listing load failure"
    js(web, app.root, "bootstrap(); 'started'")
    deadline = time.monotonic() + 10
    error_state = False
    while time.monotonic() < deadline:
        error_state = js(web, app.root,
            "document.getElementById('connectionState').textContent === 'Ошибка загрузки Marketplace'")
        if error_state:
            break
        pump(app.root, 0.1)
    assert error_state is True, "Bootstrap backend errors must not show a connected state"
    error_toast = js(web, app.root,
        "document.getElementById('toast').textContent.includes('Smoke: simulated listing load failure')")
    assert error_toast is True, "Bootstrap backend error should be visible to the user"

    client.list_error = ""
    js(web, app.root, "bootstrap(); 'retry'")
    deadline = time.monotonic() + 10
    connection_ready = False
    while time.monotonic() < deadline:
        connection_ready = js(web, app.root,
            "document.getElementById('connectionState').textContent.includes('Общая база Vkus · HTTPS')")
        if connection_ready:
            break
        pump(app.root, 0.1)
    assert connection_ready is True, "Marketplace should recover its connected state after a successful retry"
    capture(app, "vkus-marketplace-role-gate.png")

    # Both role cards must open the correct account flow.
    js(web, app.root,
       "document.querySelector('[data-role=\\\"Рекламодатель\\\"]').click(); 'ok'")
    advertiser_hint = js(web, app.root, "document.getElementById('authRoleHint').textContent")
    assert "размещаю" in advertiser_hint, "Advertiser role should open its matching auth flow"
    js(web, app.root, "document.getElementById('authBack').click(); 'back'")
    js(web, app.root,
       "document.querySelector('[data-role=\\\"Соискатель\\\"]').click(); 'ok'")
    auth_visible = js(web, app.root,
        "!document.getElementById('authModal').classList.contains('hidden')")
    assert auth_visible is True, "Role selection should open the login/registration form"
    seeker_hint = js(web, app.root, "document.getElementById('authRoleHint').textContent")
    assert "ищу" in seeker_hint, "Seeker role should open its matching auth flow"
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
    deadline = time.monotonic() + 10
    category_empty = False
    while time.monotonic() < deadline:
        category_empty = js(web, app.root, "!!document.querySelector('.empty-state')")
        if category_empty:
            break
        pump(app.root, 0.1)
    assert category_empty is True, "Category filter should affect the listing results"
    js(web, app.root, "document.getElementById('resetFilters').click(); 'reset'")
    reset_category = js(web, app.root,
        "document.querySelector('[data-category=\\\"Все категории\\\"]').classList.contains('active')")
    assert reset_category is True, "Reset should restore the all-categories chip"

    js(web, app.root, "document.getElementById('kind').value='Предлагаю'; document.getElementById('applyFilters').click(); 'kind'")
    deadline = time.monotonic() + 10
    kind_empty = False
    while time.monotonic() < deadline:
        kind_empty = js(web, app.root, "!!document.querySelector('.empty-state')")
        if kind_empty:
            break
        pump(app.root, 0.1)
    assert kind_empty is True, "Type filter should affect the listing results"
    js(web, app.root, "document.getElementById('kind').value='Ищу'; document.getElementById('applyFilters').click(); 'kind'")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        count = js(web, app.root, "document.querySelectorAll('.listing-card').length")
        if count == 1:
            break
        pump(app.root, 0.1)
    assert count == 1, "Type filter reset should restore the matching listing"

    js(web, app.root, "document.getElementById('city').value='Москва'; document.getElementById('applyFilters').click(); 'city'")
    deadline = time.monotonic() + 10
    city_empty = False
    while time.monotonic() < deadline:
        city_empty = js(web, app.root, "!!document.querySelector('.empty-state')")
        if city_empty:
            break
        pump(app.root, 0.1)
    assert city_empty is True, "City filter should affect the listing results"
    js(web, app.root, "document.getElementById('city').value='Оренбург'; document.getElementById('applyFilters').click(); 'city'")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        count = js(web, app.root, "document.querySelectorAll('.listing-card').length")
        if count == 1:
            break
        pump(app.root, 0.1)
    assert count == 1, "City filter reset should restore the matching listing"

    app.root.geometry("1366x768+0+0")
    pump(app.root, 0.5)
    card_count = js(web, app.root, "document.querySelectorAll('.listing-card').length")
    assert card_count == 1, "Listing card should remain visible at compact desktop size"
    grid_columns = js(web, app.root,
        "getComputedStyle(document.getElementById('listingGrid')).gridTemplateColumns")
    assert grid_columns, "Responsive CSS grid should be active"
    capture(app, "vkus-marketplace-board-1366x768.png")

    # Exercise the actual HTML publish form -> Python RPC -> client create path.
    js(web, app.root, "document.getElementById('resetFilters').click(); 'reset'")
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        count = js(web, app.root, "document.querySelectorAll('.listing-card').length")
        if count == 1:
            break
        pump(app.root, 0.1)
    js(web, app.root, "document.getElementById('publishButton').click(); 'publish'")
    publish_visible = js(web, app.root,
        "!document.getElementById('listingModal').classList.contains('hidden')")
    assert publish_visible is True, "Publish action should open the listing form"
    js(web, app.root, """
      document.getElementById('listingKind').value='Предлагаю';
      document.getElementById('listingCategory').value='Услуги';
      document.getElementById('listingTitle').value='Smoke: тестовая публикация';
      document.getElementById('listingDescription').value='Проверка публикации через JS и Python RPC.';
      document.getElementById('listingCity').value='Оренбург';
      document.getElementById('listingPrice').value='2500';
      document.getElementById('listingCurrency').value='RUB';
      document.getElementById('listingContact').value='@smoke';
      document.getElementById('listingSave').click();
      'submitted'
    """)
    deadline = time.monotonic() + 15
    published = False
    while time.monotonic() < deadline:
        published = js(web, app.root,
            "Array.from(document.querySelectorAll('.listing-card')).some(card => card.textContent.includes('Smoke: тестовая публикация'))")
        if published:
            break
        pump(app.root, 0.1)
    assert published is True, "Publishing through the HTML form and Python RPC should add a listing"
    assert js(web, app.root, "document.querySelectorAll('.listing-card').length") == 2, (
        "Published listing should appear alongside the existing listing"
    )

    report = {
        "result": "PASS",
        "renderer": "tkwry WebView / local HTML CSS JS",
        "tests": [
            "HTML document loaded inside real VkusApp",
            "initial Marketplace bootstrap RPC completed without navigation cancellation",
            "bootstrap backend errors show a failure state and recover after retry",
            "role gate displayed for unauthenticated user",
            "both role cards opened their matching HTML auth flow",
            "RPC login authenticated the test user",
            "listing data rendered as HTML cards",
            "keyword search produced empty state",
            "category, type and city filters changed the result set",
            "filter reset restored the listing",
            "listing publication completed through HTML-to-Python RPC",
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
