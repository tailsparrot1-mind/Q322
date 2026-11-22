"""Modern HTML/CSS Marketplace hosted inside Vkus via the existing tkwry WebView.

The browser layer is presentation only. Authentication, Supabase access, validation,
ownership checks and CRUD stay in the existing Python client.
"""
from __future__ import annotations

import os
from pathlib import Path
import tkinter as tk
from tkinter import messagebox


def open_marketplace_webview(parent):
    from .cloud_marketplace import SupabaseMarketplaceClient, CloudMarketplaceError
    from tkwry import WebView

    client = SupabaseMarketplaceClient()
    host = tk.Frame(parent, bg="#030817", bd=0, highlightthickness=0)
    host.pack(fill="both", expand=True)

    assets = Path(__file__).resolve().parent / "assets" / "marketplace_web"
    errors = []

    def fail(exc):
        errors.append(str(exc))
        try:
            messagebox.showerror(
                "Vkus Marketplace",
                "Не удалось запустить современный интерфейс Marketplace.\n\n"
                + str(exc),
                parent=parent.winfo_toplevel(),
            )
        except tk.TclError:
            pass

    web = WebView(
        host,
        app=assets,
        user_agent="VkusMarketplace/1.0",
        devtools=False,
    )
    web.when_failed(fail)
    host._marketplace_webview = web
    host._marketplace_client = client

    def public_row(row):
        allowed = (
            "id", "owner_id", "kind", "category", "title", "description",
            "city", "price", "currency", "contact", "status", "created_at",
            "updated_at",
        )
        return {key: row.get(key) for key in allowed if key in row}

    def state_payload(rows=None, error=None):
        session = client.session
        user = (session.user if session else {}) or {}
        metadata = user.get("user_metadata") or {}
        return {
            "authenticated": bool(client.is_authenticated),
            "role": metadata.get("marketplace_role") or "",
            "email": user.get("email") or "",
            "user_id": user.get("id") or "",
            "session_persistent": bool(client.session_persistence_available),
            "listings": [public_row(row) for row in (rows or [])],
            "error": error or "",
            "categories": [
                "Товары", "Услуги", "Работа", "Подряд и задачи",
                "Аренда", "Покупка", "Продажа", "Другое",
            ],
        }

    @web.rpc("marketplace_bootstrap")
    def marketplace_bootstrap():
        try:
            rows = client.list_listings(limit=100, offset=0)
            return state_payload(rows)
        except (CloudMarketplaceError, ValueError) as exc:
            return state_payload([], str(exc))

    @web.rpc("marketplace_search")
    def marketplace_search(*, search="", kind="Все типы",
                           category="Все категории", city=""):
        try:
            rows = client.list_listings(
                search=str(search or "")[:160],
                kind=kind if kind in ("Все типы", "Ищу", "Предлагаю") else "Все типы",
                category=category if category in (
                    "Все категории", "Товары", "Услуги", "Работа",
                    "Подряд и задачи", "Аренда", "Покупка", "Продажа", "Другое",
                ) else "Все категории",
                city=str(city or "")[:80],
                limit=100, offset=0,
            )
            return {"listings": [public_row(row) for row in rows], "error": ""}
        except (CloudMarketplaceError, ValueError) as exc:
            return {"listings": [], "error": str(exc)}

    @web.rpc("marketplace_sign_up")
    def marketplace_sign_up(*, email, password, role):
        try:
            client.sign_up(str(email), str(password), role=str(role))
            if client.is_authenticated:
                return {"ok": True, "authenticated": True,
                        "role": role, "message": "Регистрация завершена."}
            return {"ok": True, "authenticated": False,
                    "message": "Аккаунт создан. Подтвердите email по ссылке из письма, затем войдите."}
        except (CloudMarketplaceError, ValueError) as exc:
            return {"ok": False, "message": str(exc)}

    @web.rpc("marketplace_sign_in")
    def marketplace_sign_in(*, email, password, role):
        try:
            client.sign_in(str(email), str(password))
            saved_role = (client.session.user.get("user_metadata") or {}).get("marketplace_role")
            if saved_role not in ("Соискатель", "Рекламодатель"):
                client.set_marketplace_role(str(role))
            elif saved_role != role:
                return {"ok": False, "message": f"У аккаунта уже сохранена роль: {saved_role}. Выберите соответствующую карточку."}
            return {"ok": True, "authenticated": True, "role": role,
                    "email": client.session.user.get("email", "")}
        except (CloudMarketplaceError, ValueError) as exc:
            return {"ok": False, "message": str(exc)}

    @web.rpc("marketplace_sign_out")
    def marketplace_sign_out():
        try:
            client.sign_out()
            return {"ok": True}
        except CloudMarketplaceError as exc:
            return {"ok": False, "message": str(exc)}

    @web.rpc("marketplace_create_listing")
    def marketplace_create_listing(*, payload):
        try:
            row = client.create_listing(payload)
            return {"ok": True, "listing": public_row(row)}
        except (CloudMarketplaceError, ValueError) as exc:
            return {"ok": False, "message": str(exc)}

    @web.rpc("marketplace_update_listing")
    def marketplace_update_listing(*, listing_id, payload):
        try:
            row = client.update_listing(str(listing_id), payload)
            return {"ok": True, "listing": public_row(row)}
        except (CloudMarketplaceError, ValueError) as exc:
            return {"ok": False, "message": str(exc)}

    @web.rpc("marketplace_delete_listing")
    def marketplace_delete_listing(*, listing_id):
        try:
            client.delete_listing(str(listing_id))
            return {"ok": True}
        except CloudMarketplaceError as exc:
            return {"ok": False, "message": str(exc)}

    @web.rpc("marketplace_respond")
    def marketplace_respond(*, listing_id, message):
        try:
            client.respond_to_listing(str(listing_id), str(message))
            return {"ok": True}
        except (CloudMarketplaceError, ValueError) as exc:
            return {"ok": False, "message": str(exc)}

    @web.rpc("marketplace_get_profile")
    def marketplace_get_profile():
        try:
            return {"ok": True, "profile": client.get_my_profile()}
        except CloudMarketplaceError as exc:
            return {"ok": False, "message": str(exc)}

    @web.rpc("marketplace_save_profile")
    def marketplace_save_profile(*, display_name, city=""):
        try:
            profile = client.save_my_profile(str(display_name), str(city))
            return {"ok": True, "profile": profile}
        except (CloudMarketplaceError, ValueError) as exc:
            return {"ok": False, "message": str(exc)}

    @web.rpc("marketplace_inbox")
    def marketplace_inbox():
        try:
            rows = client.list_incoming_responses(limit=100)
            clean = []
            for row in rows:
                clean.append({
                    "id": row.get("id"),
                    "listing_id": row.get("listing_id"),
                    "listing_title": (row.get("listing") or {}).get("title", ""),
                    "sender_id": row.get("sender_id"),
                    "message": row.get("message", ""),
                    "status": row.get("status", "Новый"),
                    "created_at": row.get("created_at", ""),
                })
            return {"ok": True, "responses": clean}
        except CloudMarketplaceError as exc:
            return {"ok": False, "message": str(exc)}

    @web.rpc("marketplace_update_response")
    def marketplace_update_response(*, response_id, status):
        try:
            row = client.update_response_status(str(response_id), str(status))
            return {"ok": True, "response": row}
        except (CloudMarketplaceError, ValueError) as exc:
            return {"ok": False, "message": str(exc)}

    # Keep stable handles for integration tests and orderly teardown.
    host._marketplace_rpc_errors = errors
    host._marketplace_rpc_client = client
    host._marketplace_assets = assets
    return host
