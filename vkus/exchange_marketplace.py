"""First-party local marketplace for demand and supply listings.

The initial implementation is intentionally local-first: records are stored in
SQLite on the user's machine. No fake remote listings or unconfigured network
connectors are presented as live data.
"""
from __future__ import annotations

import sqlite3
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from datetime import datetime


KINDS = ("Ищу", "Предлагаю")
CATEGORIES = (
    "Товары", "Услуги", "Работа", "Подряд и задачи",
    "Аренда", "Покупка", "Продажа", "Другое",
)


class MarketplaceStore:
    """SQLite repository with safe parameterized search and CRUD operations."""

    def __init__(self, db_path=None):
        if db_path is None:
            db_path = Path(__file__).resolve().parent.parent / "data" / "marketplace.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self):
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS marketplace_listings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL CHECK(kind IN ('Ищу','Предлагаю')),
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    city TEXT NOT NULL,
                    price TEXT NOT NULL DEFAULT '',
                    contact TEXT NOT NULL DEFAULT '',
                    author TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'Активно'
                        CHECK(status IN ('Активно','Завершено','Архив')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_marketplace_status ON marketplace_listings(status, created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_marketplace_city ON marketplace_listings(city)")

    @staticmethod
    def _validate(payload):
        required = ("kind", "category", "title", "description", "city")
        for key in required:
            if not str(payload.get(key, "")).strip():
                raise ValueError("Заполните обязательные поля: тип, категория, заголовок, описание и город.")
        if payload["kind"] not in KINDS:
            raise ValueError("Неизвестный тип объявления.")
        if payload["category"] not in CATEGORIES:
            raise ValueError("Выберите категорию из списка.")
        if len(payload["title"].strip()) > 120:
            raise ValueError("Заголовок не должен превышать 120 символов.")
        if len(payload["description"].strip()) > 5000:
            raise ValueError("Описание не должно превышать 5000 символов.")
        if len(payload["city"].strip()) > 80:
            raise ValueError("Название города слишком длинное.")

    def create(self, payload):
        self._validate(payload)
        now = datetime.now().isoformat(timespec="seconds")
        values = (
            payload["kind"].strip(), payload["category"].strip(),
            payload["title"].strip(), payload["description"].strip(),
            payload["city"].strip(), payload.get("price", "").strip(),
            payload.get("contact", "").strip(), payload.get("author", "").strip(),
            now, now,
        )
        with self._connect() as conn:
            cur = conn.execute("""
                INSERT INTO marketplace_listings
                (kind,category,title,description,city,price,contact,author,status,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?, 'Активно',?,?)
            """, values)
            return cur.lastrowid

    def update(self, listing_id, payload):
        self._validate(payload)
        now = datetime.now().isoformat(timespec="seconds")
        values = (
            payload["kind"].strip(), payload["category"].strip(),
            payload["title"].strip(), payload["description"].strip(),
            payload["city"].strip(), payload.get("price", "").strip(),
            payload.get("contact", "").strip(), payload.get("author", "").strip(),
            now, int(listing_id),
        )
        with self._connect() as conn:
            cur = conn.execute("""
                UPDATE marketplace_listings SET kind=?,category=?,title=?,description=?,
                city=?,price=?,contact=?,author=?,updated_at=? WHERE id=?
            """, values)
            if not cur.rowcount:
                raise LookupError("Объявление не найдено.")

    def set_status(self, listing_id, status):
        if status not in ("Активно", "Завершено", "Архив"):
            raise ValueError("Недопустимый статус объявления.")
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE marketplace_listings SET status=?,updated_at=? WHERE id=?",
                (status, datetime.now().isoformat(timespec="seconds"), int(listing_id)),
            )
            if not cur.rowcount:
                raise LookupError("Объявление не найдено.")

    def delete(self, listing_id):
        with self._connect() as conn:
            conn.execute("DELETE FROM marketplace_listings WHERE id=?", (int(listing_id),))

    def get(self, listing_id):
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM marketplace_listings WHERE id=?", (int(listing_id),)
            ).fetchone()
            return dict(row) if row else None

    def list_listings(self, query="", kind="Все типы", category="Все категории",
                      city="", status="Активно"):
        sql = "SELECT * FROM marketplace_listings WHERE 1=1"
        args = []
        if status != "Все статусы":
            sql += " AND status=?"
            args.append(status)
        if kind != "Все типы":
            sql += " AND kind=?"
            args.append(kind)
        if category != "Все категории":
            sql += " AND category=?"
            args.append(category)
        if city.strip():
            sql += " AND city LIKE ?"
            args.append("%" + city.strip() + "%")
        if query.strip():
            sql += " AND (title LIKE ? OR description LIKE ? OR city LIKE ? OR category LIKE ?)"
            term = "%" + query.strip() + "%"
            args.extend((term, term, term, term))
        sql += " ORDER BY CASE status WHEN 'Активно' THEN 0 WHEN 'Завершено' THEN 1 ELSE 2 END, created_at DESC"
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(sql, args).fetchall()]


def open_marketplace_window(parent):
    """Open the working local demand/supply board."""
    store = MarketplaceStore()
    win = tk.Toplevel(parent)
    win.title("Vkus — Биржа объявлений")
    win.configure(bg="#030817")
    win.geometry("1120x720")
    win.minsize(900, 600)
    win.transient(parent)

    style = ttk.Style(win)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("Market.Treeview", background="#0a1731", fieldbackground="#0a1731",
                    foreground="#eaf1ff", rowheight=34, borderwidth=0,
                    font=("DejaVu Sans", 9))
    style.configure("Market.Treeview.Heading", background="#17264a",
                    foreground="#c99aff", font=("DejaVu Sans", 9, "bold"))
    style.map("Market.Treeview", background=[("selected", "#4b258b")])
    style.configure("TCombobox", fieldbackground="#0a1731", background="#17264a",
                    foreground="#eaf1ff", arrowcolor="#c99aff",
                    bordercolor="#304b80", lightcolor="#304b80", darkcolor="#304b80")
    style.map("TCombobox", fieldbackground=[("readonly", "#0a1731")],
              foreground=[("readonly", "#eaf1ff")],
              selectbackground=[("readonly", "#0a1731")],
              selectforeground=[("readonly", "#eaf1ff")])

    shell = tk.Frame(win, bg="#07132d", highlightbackground="#8548dc", highlightthickness=1)
    shell.pack(fill="both", expand=True, padx=0, pady=0)
    header = tk.Frame(shell, bg="#07122a")
    header.pack(fill="x", padx=18, pady=(16, 8))
    tk.Label(header, text="БИРЖА СПРОСА И ПРЕДЛОЖЕНИЙ", bg="#07122a",
             fg="#d18aff", font=("DejaVu Sans", 17, "bold")).pack(side="left")
    tk.Label(header, text="Локальная доска объявлений · данные хранятся на этом компьютере",
             bg="#07122a", fg="#8da4d3", font=("DejaVu Sans", 8)).pack(side="right")

    filters = tk.Frame(shell, bg="#07122a")
    filters.pack(fill="x", padx=18, pady=(4, 10))
    query_var = tk.StringVar()
    kind_var = tk.StringVar(value="Все типы")
    category_var = tk.StringVar(value="Все категории")
    city_var = tk.StringVar()
    status_var = tk.StringVar(value="Активно")
    def field(parent_frame, caption, widget_type, **widget_options):
        cell = tk.Frame(parent_frame, bg="#07122a")
        cell.pack(side="left", padx=(0, 10), anchor="n")
        tk.Label(cell, text=caption, bg="#07122a", fg="#91a8d7",
                 font=("DejaVu Sans", 8)).pack(anchor="w")
        widget = widget_type(cell, **widget_options)
        widget.pack(fill="x", pady=(3, 0))
        return widget
    field(filters, "Поиск по объявлениям", tk.Entry, textvariable=query_var,
          bg="#0a1731", fg="#f0f4ff", insertbackground="white", relief="flat",
          width=27, font=("DejaVu Sans", 9))
    field(filters, "Тип", ttk.Combobox, textvariable=kind_var,
          values=("Все типы",) + KINDS, state="readonly", width=12)
    field(filters, "Категория", ttk.Combobox, textvariable=category_var,
          values=("Все категории",) + CATEGORIES, state="readonly", width=19)
    field(filters, "Статус", ttk.Combobox, textvariable=status_var,
          values=("Активно", "Завершено", "Архив", "Все статусы"),
          state="readonly", width=12)
    field(filters, "Город", tk.Entry, textvariable=city_var, bg="#0a1731",
          fg="#f0f4ff", insertbackground="white", relief="flat", width=15,
          font=("DejaVu Sans", 9))

    body = tk.Frame(shell, bg="#07122a")
    body.pack(fill="both", expand=True, padx=18, pady=(0, 10))
    columns = ("kind", "title", "category", "city", "price", "created_at")
    table = ttk.Treeview(body, columns=columns, show="headings", style="Market.Treeview")
    headings = {"kind":"Тип", "title":"Объявление", "category":"Категория",
                "city":"Город", "price":"Цена / бюджет", "created_at":"Создано"}
    widths = {"kind":95, "title":330, "category":145, "city":130, "price":130, "created_at":145}
    for key in columns:
        table.heading(key, text=headings[key])
        table.column(key, width=widths[key], anchor="w")
    scroll = ttk.Scrollbar(body, orient="vertical", command=table.yview)
    table.configure(yscrollcommand=scroll.set)
    table.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")

    details = tk.Label(shell, text="Выберите объявление, чтобы увидеть описание и контакты.",
                       bg="#0a1731", fg="#9fb4df", justify="left", anchor="w",
                       padx=12, pady=9, font=("DejaVu Sans", 9))
    details.pack(fill="x", padx=24, pady=(0, 10))
    actions = tk.Frame(shell, bg="#07122a")
    actions.pack(fill="x", padx=18, pady=(0, 16))
    count_label = tk.Label(actions, text="", bg="#07122a", fg="#8fa5d4",
                           font=("DejaVu Sans", 8))
    count_label.pack(side="left")

    current = {}
    def selected_id():
        selection = table.selection()
        return int(selection[0]) if selection else None

    def show_details(_event=None):
        listing_id = selected_id()
        item = store.get(listing_id) if listing_id else None
        if not item:
            details.configure(text="Выберите объявление, чтобы увидеть описание и контакты.")
            return
        text = (f"{item['kind']} · {item['category']} · {item['status']}\n"
                f"{item['title']}\n{item['description']}\n"
                f"Город: {item['city']}   Бюджет/цена: {item['price'] or 'не указана'}\n"
                f"Автор: {item['author'] or 'не указан'}   Контакт: {item['contact'] or 'не указан'}")
        details.configure(text=text)

    def refresh(*_):
        rows = store.list_listings(query_var.get(), kind_var.get(), category_var.get(),
                                   city_var.get(), status_var.get())
        table.delete(*table.get_children())
        for item in rows:
            table.insert("", "end", iid=str(item["id"]), values=(
                item["kind"], item["title"], item["category"], item["city"],
                item["price"] or "—", item["created_at"][:16].replace("T", " "),
            ))
        count_label.configure(text=f"Объявлений: {len(rows)}")
        show_details()

    def edit_dialog(existing=None):
        dialog = tk.Toplevel(win)
        dialog.title("Новое объявление" if existing is None else "Редактировать объявление")
        dialog.configure(bg="#091735")
        dialog.transient(win)
        dialog.grab_set()
        dialog.geometry("610x600")
        form = tk.Frame(dialog, bg="#091735")
        form.pack(fill="both", expand=True, padx=22, pady=18)
        values = {
            "kind": tk.StringVar(value=(existing or {}).get("kind", "Ищу")),
            "category": tk.StringVar(value=(existing or {}).get("category", CATEGORIES[0])),
            "title": tk.StringVar(value=(existing or {}).get("title", "")),
            "city": tk.StringVar(value=(existing or {}).get("city", "")),
            "price": tk.StringVar(value=(existing or {}).get("price", "")),
            "author": tk.StringVar(value=(existing or {}).get("author", "")),
            "contact": tk.StringVar(value=(existing or {}).get("contact", "")),
        }
        def row(caption, widget):
            tk.Label(form, text=caption, bg="#091735", fg="#a9badc",
                     font=("DejaVu Sans", 9, "bold")).pack(anchor="w", pady=(9, 2))
            widget.pack(fill="x", ipady=5)
        row("Тип объявления *", ttk.Combobox(form, textvariable=values["kind"],
            values=KINDS, state="readonly"))
        row("Категория *", ttk.Combobox(form, textvariable=values["category"],
            values=CATEGORIES, state="readonly"))
        row("Заголовок *", tk.Entry(form, textvariable=values["title"], bg="#102044",
            fg="white", insertbackground="white", relief="flat"))
        row("Город *", tk.Entry(form, textvariable=values["city"], bg="#102044",
            fg="white", insertbackground="white", relief="flat"))
        row("Цена / бюджет", tk.Entry(form, textvariable=values["price"], bg="#102044",
            fg="white", insertbackground="white", relief="flat"))
        row("Автор / организация", tk.Entry(form, textvariable=values["author"], bg="#102044",
            fg="white", insertbackground="white", relief="flat"))
        row("Контакт (телефон, ссылка или ник)", tk.Entry(form, textvariable=values["contact"],
            bg="#102044", fg="white", insertbackground="white", relief="flat"))
        tk.Label(form, text="Описание *", bg="#091735", fg="#a9badc",
                 font=("DejaVu Sans", 9, "bold")).pack(anchor="w", pady=(9, 2))
        description = tk.Text(form, height=5, bg="#102044", fg="white",
                              insertbackground="white", relief="flat", wrap="word")
        description.pack(fill="both", expand=True)
        description.insert("1.0", (existing or {}).get("description", ""))
        def save():
            payload = {key: var.get().strip() for key, var in values.items()}
            payload["description"] = description.get("1.0", "end-1c").strip()
            try:
                if existing:
                    store.update(existing["id"], payload)
                else:
                    store.create(payload)
            except (ValueError, LookupError) as exc:
                messagebox.showwarning("Проверьте объявление", str(exc), parent=dialog)
                return
            dialog.destroy()
            refresh()
        buttons = tk.Frame(form, bg="#091735")
        buttons.pack(fill="x", pady=(12, 0))
        tk.Button(buttons, text="СОХРАНИТЬ", command=save, bg="#6330b4", fg="white",
                  activebackground="#8549df", relief="flat", padx=18, pady=8).pack(side="right")
        tk.Button(buttons, text="ОТМЕНА", command=dialog.destroy, bg="#17264a", fg="#dbe6ff",
                  relief="flat", padx=16, pady=8).pack(side="right", padx=8)

    def add():
        edit_dialog()
    def edit():
        listing_id = selected_id()
        item = store.get(listing_id) if listing_id else None
        if item:
            edit_dialog(item)
        else:
            messagebox.showinfo("Биржа", "Сначала выберите объявление.", parent=win)
    def change_status(status):
        listing_id = selected_id()
        if not listing_id:
            messagebox.showinfo("Биржа", "Сначала выберите объявление.", parent=win)
            return
        store.set_status(listing_id, status)
        refresh()
    def remove():
        listing_id = selected_id()
        if not listing_id:
            messagebox.showinfo("Биржа", "Сначала выберите объявление.", parent=win)
            return
        if messagebox.askyesno("Удалить объявление", "Удалить выбранное объявление без возможности восстановления?", parent=win):
            store.delete(listing_id)
            refresh()

    def action(text, command, color="#182b55"):
        tk.Button(actions, text=text, command=command, bg=color, fg="white",
                  activebackground="#7540c8", activeforeground="white",
                  relief="flat", bd=0, padx=12, pady=7,
                  font=("DejaVu Sans", 8, "bold"), cursor="hand2").pack(side="right", padx=(6,0))
    action("Удалить", remove, "#64263f")
    action("В архив", lambda: change_status("Архив"))
    action("Завершено", lambda: change_status("Завершено"))
    action("Редактировать", edit)
    action("+ Добавить объявление", add, "#6330b4")

    table.bind("<<TreeviewSelect>>", show_details)
    for var in (query_var, kind_var, category_var, city_var, status_var):
        var.trace_add("write", refresh)
    refresh()
    win.bind("<Escape>", lambda _e: win.destroy())
    return win



def open_cloud_marketplace_window(parent):
    """Build the announcement board inside the existing Vkus content area."""
    from .cloud_marketplace import SupabaseMarketplaceClient, CloudMarketplaceError

    client = SupabaseMarketplaceClient()
    win = tk.Frame(parent, bg="#050b1b", bd=0, highlightthickness=0)
    win.pack(fill="both", expand=True)

    style = ttk.Style(parent.winfo_toplevel())
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("CloudMarket.Treeview", background="#081832",
                    fieldbackground="#081832", foreground="#edf4ff",
                    rowheight=40, borderwidth=0, relief="flat",
                    font=("DejaVu Sans", 9))
    style.map("CloudMarket.Treeview",
              background=[("selected", "#38216d")],
              foreground=[("selected", "#ffffff")])
    style.layout("CloudMarket.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    style.configure("CloudMarket.Vertical.TScrollbar", troughcolor="#061126",
                    background="#31538c", bordercolor="#061126",
                    arrowcolor="#45dcff", relief="flat", width=11)
    style.map("CloudMarket.Vertical.TScrollbar",
              background=[("active", "#6b3bc1")])
    style.map("CloudMarket.Vertical.TScrollbar",
              background=[("active", "#7540c8")])
    style.configure("CloudMarket.Treeview.Heading", background="#102b52",
                    foreground="#42ddff", font=("DejaVu Sans", 8, "bold"),
                    padding=(10, 9), relief="flat")
    style.map("CloudMarket.Treeview", background=[("selected", "#4b258b")])
    style.configure("TCombobox", fieldbackground="#0a1731", background="#17264a",
                    foreground="#eaf1ff", arrowcolor="#c99aff", bordercolor="#304b80",
                    lightcolor="#304b80", darkcolor="#304b80", font=("DejaVu Sans", 9))
    style.map("TCombobox", fieldbackground=[("readonly", "#0a1731")],
              foreground=[("readonly", "#eaf1ff")],
              selectbackground=[("readonly", "#0a1731")],
              selectforeground=[("readonly", "#eaf1ff")],
              background=[("readonly", "#17264a")])

    shell = tk.Frame(win, bg="#07142d", highlightbackground="#7136c3",
                     highlightthickness=1)
    shell.pack(fill="both", expand=True, padx=8, pady=8)
    header = tk.Frame(shell, bg="#07122a")
    header.pack(fill="x", padx=22, pady=(16, 10))
    heading_block = tk.Frame(header, bg="#07122a")
    heading_block.pack(side="left", fill="x", expand=True)
    tk.Label(heading_block, text="ДОСКА ОБЪЯВЛЕНИЙ", bg="#07122a",
             fg="#d9a0ff", font=("DejaVu Sans", 20, "bold")).pack(anchor="w")
    tk.Label(heading_block, text="Маркетплейс услуг, товаров, работы и запросов",
             bg="#07122a", fg="#8fa9d7",
             font=("DejaVu Sans", 9)).pack(anchor="w", pady=(2, 0))
    account_pill = tk.Frame(header, bg="#0d2546",
                            highlightbackground="#24618a", highlightthickness=1)
    account_pill.pack(side="right", padx=4, pady=3)
    account_label = tk.Label(account_pill, text="Не выполнен вход",
                             bg="#0d2546", fg="#9fdcff",
                             font=("DejaVu Sans", 8, "bold"),
                             padx=12, pady=8)
    account_label.pack()

    def update_account_label(display_name=None):
        session = getattr(client, "session", None)
        if not session or not getattr(session, "user", None):
            account_label.configure(text="Не выполнен вход", fg="#9fb4df")
            return
        name = display_name or session.user.get("email", "Вход выполнен")
        if client.session_persistence_available:
            account_label.configure(text=f"●  {name} · защищённая сессия",
                                     fg="#61efbd", bg="#0d2546")
        else:
            account_label.configure(text=f"●  {name} · до закрытия",
                                     fg="#ffd17b", bg="#0d2546")

    update_account_label()

    auth_bar = tk.Frame(shell, bg="#0a1731")
    auth_bar.pack(fill="x", padx=24, pady=(0, 14))
    email_var = tk.StringVar()
    password_var = tk.StringVar()
    tk.Label(auth_bar, text="Email", bg="#0a1731", fg="#9fb4df",
             font=("DejaVu Sans", 8)).pack(side="left", padx=(10, 4))
    tk.Entry(auth_bar, textvariable=email_var, width=27, bg="#102044", fg="white",
             insertbackground="white", relief="flat", bd=0, highlightthickness=1,
             highlightbackground="#304b80", highlightcolor="#8d4cff").pack(side="left", padx=4, pady=8, ipady=4)
    tk.Label(auth_bar, text="Пароль", bg="#0a1731", fg="#9fb4df",
             font=("DejaVu Sans", 8)).pack(side="left", padx=(10, 4))
    tk.Entry(auth_bar, textvariable=password_var, show="•", width=20, bg="#102044",
             fg="white", insertbackground="white", relief="flat", bd=0, highlightthickness=1,
             highlightbackground="#304b80", highlightcolor="#8d4cff").pack(side="left", padx=4, pady=8, ipady=4)

    filters_shell = tk.Frame(shell, bg="#0a1a38",
                             highlightbackground="#203f70", highlightthickness=1)
    filters_shell.pack(fill="x", padx=22, pady=(0, 12))
    filters = tk.Frame(filters_shell, bg="#0a1a38")
    filters.pack(fill="x", padx=14, pady=12)
    query_var = tk.StringVar()
    kind_var = tk.StringVar(value="Все типы")
    category_var = tk.StringVar(value="Все категории")
    city_var = tk.StringVar()
    filter_cells = []
    def filter_field(caption, widget_type, **options):
        cell = tk.Frame(filters, bg="#0a1a38")
        filter_cells.append(cell)
        tk.Label(cell, text=caption.upper(), bg="#0a1a38", fg="#9ab2df",
                 font=("DejaVu Sans", 7, "bold")).pack(anchor="w", pady=(0, 2))
        widget = widget_type(cell, **options)
        widget.pack(fill="x", pady=(3, 0))
        return widget
    query_entry = filter_field("Поиск", tk.Entry, textvariable=query_var, width=28,
                 bg="#0a1731", fg="white", insertbackground="white", relief="flat",
                 bd=0, highlightthickness=1, highlightbackground="#34527f",
                 highlightcolor="#b34cff", font=("DejaVu Sans", 9))
    query_entry.bind("<Return>", lambda _event: refresh())
    filter_field("Тип", ttk.Combobox, textvariable=kind_var,
                 values=("Все типы",) + KINDS, state="readonly", width=13)
    filter_field("Категория", ttk.Combobox, textvariable=category_var,
                 values=("Все категории",) + CATEGORIES, state="readonly", width=19)
    filter_field("Город", tk.Entry, textvariable=city_var, width=17,
                 bg="#0a1731", fg="white", insertbackground="white", relief="flat",
                 bd=0, highlightthickness=1, highlightbackground="#304b80",
                 highlightcolor="#8d4cff", font=("DejaVu Sans", 9))

    search_actions = tk.Frame(filters, bg="#0a1a38")
    tk.Button(search_actions, text="НАЙТИ", command=lambda: refresh(),
              bg="#6f35c5", fg="white", activebackground="#8e4de5",
              activeforeground="white", relief="flat", bd=0,
              padx=17, pady=8, cursor="hand2",
              font=("DejaVu Sans", 8, "bold")).pack(side="left", padx=(0, 6))
    reset_button = tk.Button(search_actions, text="СБРОСИТЬ",
              command=lambda: (query_var.set(""), kind_var.set("Все типы"),
                               category_var.set("Все категории"), city_var.set("")),
              bg="#142b4d", fg="#c7d9f7", activebackground="#204474",
              relief="flat", bd=0, padx=12, pady=8, cursor="hand2",
              font=("DejaVu Sans", 8, "bold"))
    reset_button.pack(side="left")

    def layout_filter_controls(_event=None):
        # The search row is split on compact windows so the reset action never
        # falls outside the panel. The same controls remain visible and usable.
        compact = filters.winfo_width() < 1080
        for cell in filter_cells:
            cell.grid_forget()
        search_actions.grid_forget()
        if compact:
            placements = ((0, 0), (0, 1), (0, 2), (1, 0))
            for cell, (row, column) in zip(filter_cells, placements):
                cell.grid(row=row, column=column, sticky="ew",
                          padx=(0, 10), pady=(0, 6) if row == 0 else (2, 0))
            search_actions.grid(row=1, column=1, columnspan=2,
                                sticky="w", padx=(2, 0), pady=(14, 0))
            for column in range(3):
                filters.grid_columnconfigure(column, weight=1)
            filters.grid_columnconfigure(3, weight=0)
        else:
            for column, cell in enumerate(filter_cells):
                cell.grid(row=0, column=column, sticky="ew",
                          padx=(0, 12), pady=0)
                filters.grid_columnconfigure(column, weight=0)
            search_actions.grid(row=0, column=len(filter_cells),
                                sticky="w", padx=(2, 0), pady=(14, 0))
            filters.grid_columnconfigure(len(filter_cells), weight=0)

    filters.bind("<Configure>", layout_filter_controls)

    body = tk.Frame(shell, bg="#07122a")
    body.pack(fill="both", expand=True, padx=22, pady=(0, 10))
    cards_canvas = tk.Canvas(body, bg="#07122a", highlightthickness=0, bd=0)
    cards_scroll = ttk.Scrollbar(body, orient="vertical", command=cards_canvas.yview,
                                 style="CloudMarket.Vertical.TScrollbar")
    cards_canvas.configure(yscrollcommand=cards_scroll.set)
    cards_canvas.pack(side="left", fill="both", expand=True)
    cards_scroll.pack(side="right", fill="y")
    cards_frame = tk.Frame(cards_canvas, bg="#07122a")
    cards_window = cards_canvas.create_window((0, 0), window=cards_frame, anchor="nw")
    cards_frame.bind("<Configure>", lambda _e: cards_canvas.configure(
        scrollregion=cards_canvas.bbox("all")))
    cards_canvas.bind("<Configure>", lambda event: cards_canvas.itemconfigure(
        cards_window, width=event.width))
    cards_frame.grid_columnconfigure(0, weight=1, uniform="market-cards")
    cards_frame.grid_columnconfigure(1, weight=1, uniform="market-cards")

    details_shell = tk.Frame(shell, bg="#0b1d3b",
                             highlightbackground="#31517e", highlightthickness=1)
    details_shell.pack(fill="x", padx=22, pady=(0, 8))
    details = tk.Label(details_shell,
                       text="Выберите карточку, чтобы увидеть полное описание и контакт.",
                       bg="#0b1d3b", fg="#b9cbea", justify="left", anchor="w",
                       padx=14, pady=10, font=("DejaVu Sans", 9),
                       wraplength=1100)
    details.pack(fill="x")
    def resize_details(event):
        details.configure(wraplength=max(320, event.width - 52))
    details_shell.bind("<Configure>", resize_details)
    actions = tk.Frame(shell, bg="#07122a")
    actions.pack(fill="x", padx=22, pady=(0, 12))
    status_label = tk.Label(actions, text="Общая база Supabase · HTTPS",
                            bg="#07122a", fg="#8fa5d4", font=("DejaVu Sans", 8))
    status_label.pack(side="left")
    rows_by_id = {}
    selected_id = {"value": None}

    def notify_error(exc):
        messagebox.showerror("Доска объявлений", str(exc), parent=win)

    def selected():
        return rows_by_id.get(selected_id["value"])

    def refresh(*_):
        try:
            rows = client.list_listings(
                search=query_var.get(), kind=kind_var.get(),
                category=category_var.get(), city=city_var.get(),
                limit=100, offset=0,
            )
        except (CloudMarketplaceError, ValueError) as exc:
            notify_error(exc)
            return
        rows_by_id.clear()
        selected_id["value"] = None
        for child in cards_frame.winfo_children():
            child.destroy()
        if not rows:
            empty = tk.Frame(cards_frame, bg="#0d1e3d",
                             highlightbackground="#6840a4", highlightthickness=1)
            empty.grid(row=0, column=0, columnspan=2, sticky="nsew",
                       padx=8, pady=8, ipady=38)
            tk.Label(empty, text="ЗДЕСЬ ПОЯВЯТСЯ ОБЪЯВЛЕНИЯ",
                     bg="#0d1e3d", fg="#dca4ff",
                     font=("DejaVu Sans", 14, "bold")).pack(pady=(22, 8))
            tk.Label(empty, text="Ищите нужные предложения или опубликуйте своё — "
                     "объявление станет доступно пользователям маркетплейса.",
                     bg="#0d1e3d", fg="#b6c9eb", font=("DejaVu Sans", 9),
                     wraplength=760, justify="center").pack(pady=(0, 18))
        available_width = max(520, cards_canvas.winfo_width() - 72)
        card_wrap = (max(280, available_width - 24) if len(rows) == 1
                     else max(210, (available_width - 28) // 2))
        for index, item in enumerate(rows):
            key = str(item["id"])
            rows_by_id[key] = item
            kind = item.get("kind") or "Ищу"
            accent = "#b75cff" if kind == "Ищу" else "#24bde9"
            card = tk.Frame(cards_frame, bg="#0d1d3b",
                            highlightbackground="#31517e", highlightthickness=1,
                            padx=16, pady=14)
            card.grid(row=index // 2, column=index % 2,
                      columnspan=2 if len(rows) == 1 else 1,
                      sticky="nsew", padx=8, pady=8)
            # Slim neon rail makes each listing instantly scannable.
            stripe = tk.Frame(card, bg=accent, width=4)
            stripe.place(x=0, y=0, relheight=1)
            top = tk.Frame(card, bg="#101f43")
            top.pack(fill="x", padx=(5, 0))
            badge_bg = "#2b1555" if kind == "Ищу" else "#103c55"
            badge_text = "ИЩУ" if kind == "Ищу" else "ПРЕДЛАГАЮ"
            tk.Label(top, text=badge_text, bg=badge_bg, fg=accent,
                     font=("DejaVu Sans", 8, "bold"),
                     padx=12, pady=5).pack(side="left")
            created = (item.get("created_at") or "")[:10]
            tk.Label(top, text=f"ОПУБЛИКОВАНО  {created or '—'}",
                     bg="#101f43", fg="#8098c6",
                     font=("DejaVu Sans", 7, "bold")).pack(side="right", padx=(4, 2))
            tk.Label(card, text=item.get("title") or "Без заголовка",
                     bg="#0d1d3b", fg="#f6f3ff",
                     font=("DejaVu Sans", 13, "bold"),
                     anchor="w", justify="left", wraplength=card_wrap).pack(
                         fill="x", padx=(5, 0), pady=(12, 6))
            summary = (item.get("description") or "").replace("\n", " ").strip()
            if len(summary) > 220:
                summary = summary[:217] + "…"
            tk.Label(card, text=summary or "Автор пока не добавил описание.",
                     bg="#0d1d3b", fg="#b8c7e6",
                     font=("DejaVu Sans", 9), anchor="w", justify="left",
                     wraplength=card_wrap).pack(fill="x", padx=(5, 0), pady=(0, 12))
            meta_row = tk.Frame(card, bg="#0d1d3b")
            meta_row.pack(fill="x", padx=(5, 0))
            def meta_chip(caption, value, color="#d8c5ff", fill="#1a2c53"):
                tk.Label(meta_row, text=f"{caption}  {value}", bg=fill, fg=color,
                         font=("DejaVu Sans", 8, "bold"),
                         padx=10, pady=6).pack(side="left", padx=(0, 8))
            meta_chip("КАТЕГОРИЯ", item.get("category") or "Другое")
            meta_chip("ГОРОД", f"⌖ {item.get('city') or 'Не указан'}", "#b9d8ff", "#142b50")
            if item.get("price") not in (None, ""):
                price = f"{item.get('price')} {item.get('currency') or 'RUB'}"
                meta_chip("БЮДЖЕТ" if kind == "Ищу" else "ЦЕНА", price,
                          "#83f0df" if kind == "Ищу" else "#8be7ff",
                          "#103b4a" if kind == "Ищу" else "#10354b")
            status_text = item.get("status") or "Активно"
            tk.Label(meta_row, text=status_text.upper(), bg="#101f43",
                     fg="#6fe0b4" if status_text == "Активно" else "#a2b0ce",
                     font=("DejaVu Sans", 7, "bold")).pack(side="right", padx=(4, 2))
            def choose(_event=None, listing_key=key, selected_card=card):
                selected_id["value"] = listing_key
                for sibling in cards_frame.winfo_children():
                    if isinstance(sibling, tk.Frame):
                        sibling.configure(highlightbackground="#31517e")
                selected_card.configure(highlightbackground="#d04cff")
                show_details()
            def bind_card_clicks(widget):
                widget.bind("<Button-1>", choose, add="+")
                for child in widget.winfo_children():
                    bind_card_clicks(child)
            bind_card_clicks(card)
        status_label.configure(text=f"Объявлений в общей базе: {len(rows)}")
        show_details()

    def show_details(_event=None):
        item = selected()
        if not item:
            details.configure(text="Выберите объявление, чтобы увидеть описание и контакт.")
            return
        own = bool(client.session and item.get("owner_id") == client.session.user.get("id"))
        details.configure(text=(
            f"{item['kind']} · {item['category']}\n{item['title']}\n"
            f"{item['description']}\nГород: {item['city']} · "
            f"Цена/бюджет: {item.get('price') or 'не указана'} {item.get('currency') or 'RUB'}\n"
            f"Контакт: {item.get('contact') or 'не указан'}"
            + (" · Ваше объявление" if own else "")
        ))

    def sign_in():
        try:
            client.sign_in(email_var.get(), password_var.get())
            profile = client.get_my_profile()
            update_account_label(profile.get("display_name"))
            refresh()
        except (CloudMarketplaceError, ValueError) as exc:
            notify_error(exc)

    def sign_up():
        try:
            result = client.sign_up(email_var.get(), password_var.get())
            if client.is_authenticated:
                update_account_label()
                refresh()
            else:
                messagebox.showinfo(
                    "Подтверждение email",
                    "Аккаунт создан. Если включено подтверждение email, откройте письмо Supabase, "
                    "подтвердите адрес и затем войдите.",
                    parent=win,
                )
        except (CloudMarketplaceError, ValueError) as exc:
            notify_error(exc)

    def sign_out():
        try:
            client.sign_out()
        except CloudMarketplaceError as exc:
            notify_error(exc)
        account_label.configure(text="Не выполнен вход", fg="#9fb4df")
        refresh()
        gate.place(in_=shell, x=0, y=0, relwidth=1, relheight=1)
        gate.lift()

    def edit_profile():
        if not client.is_authenticated:
            messagebox.showinfo("Профиль", "Сначала войдите в аккаунт.", parent=win)
            return
        try:
            current = client.get_my_profile()
        except CloudMarketplaceError as exc:
            notify_error(exc)
            return
        dialog = tk.Toplevel(win)
        dialog.title("Профиль Vkus")
        dialog.configure(bg="#091735")
        dialog.transient(win)
        dialog.grab_set()
        dialog.geometry("430x260")
        form = tk.Frame(dialog, bg="#091735")
        form.pack(fill="both", expand=True, padx=22, pady=18)
        name_var = tk.StringVar(value=current.get("display_name") or
                                client.session.user.get("email", "").split("@")[0])
        city_var = tk.StringVar(value=current.get("city") or "")
        for caption, variable in (("Имя / название организации", name_var), ("Город", city_var)):
            tk.Label(form, text=caption, bg="#091735", fg="#a9badc",
                     font=("DejaVu Sans", 9, "bold")).pack(anchor="w", pady=(8, 2))
            tk.Entry(form, textvariable=variable, bg="#102044", fg="white",
                     insertbackground="white", relief="flat").pack(fill="x", ipady=5)
        def save_profile():
            try:
                saved = client.save_my_profile(name_var.get(), city_var.get())
            except (CloudMarketplaceError, ValueError) as exc:
                notify_error(exc)
                return
            account_label.configure(text=saved.get("display_name") or name_var.get(),
                                     fg="#16f0a1")
            dialog.destroy()
        tk.Button(form, text="СОХРАНИТЬ ПРОФИЛЬ", command=save_profile,
                  bg="#6330b4", fg="white", relief="flat", padx=14, pady=8).pack(
                      anchor="e", pady=(18, 0))

    def create_or_edit(existing=None):
        if not client.is_authenticated:
            messagebox.showinfo("Облачная биржа", "Сначала войдите или создайте аккаунт.", parent=win)
            return
        dialog = tk.Toplevel(win)
        dialog.title("Новое объявление" if existing is None else "Редактирование объявления")
        dialog.configure(bg="#091735")
        dialog.transient(win)
        dialog.grab_set()
        dialog.geometry("600x590")
        form = tk.Frame(dialog, bg="#091735")
        form.pack(fill="both", expand=True, padx=22, pady=16)
        values = {
            "kind": tk.StringVar(value=(existing or {}).get("kind", "Ищу")),
            "category": tk.StringVar(value=(existing or {}).get("category", CATEGORIES[0])),
            "title": tk.StringVar(value=(existing or {}).get("title", "")),
            "city": tk.StringVar(value=(existing or {}).get("city", "")),
            "price": tk.StringVar(value=str((existing or {}).get("price") or "")),
            "currency": tk.StringVar(value=(existing or {}).get("currency", "RUB")),
            "contact": tk.StringVar(value=(existing or {}).get("contact", "")),
        }
        def row(caption, widget):
            tk.Label(form, text=caption, bg="#091735", fg="#a9badc",
                     font=("DejaVu Sans", 9, "bold")).pack(anchor="w", pady=(8, 2))
            widget.pack(fill="x", ipady=4)
        row("Тип объявления", ttk.Combobox(form, textvariable=values["kind"],
            values=KINDS, state="readonly"))
        row("Категория", ttk.Combobox(form, textvariable=values["category"],
            values=CATEGORIES, state="readonly"))
        row("Заголовок", tk.Entry(form, textvariable=values["title"], bg="#102044",
            fg="white", insertbackground="white", relief="flat"))
        row("Город", tk.Entry(form, textvariable=values["city"], bg="#102044",
            fg="white", insertbackground="white", relief="flat"))
        row("Цена / бюджет (число)", tk.Entry(form, textvariable=values["price"], bg="#102044",
            fg="white", insertbackground="white", relief="flat"))
        row("Валюта", ttk.Combobox(form, textvariable=values["currency"],
            values=("RUB", "EUR", "USD"), state="readonly"))
        row("Контакт", tk.Entry(form, textvariable=values["contact"], bg="#102044",
            fg="white", insertbackground="white", relief="flat"))
        tk.Label(form, text="Описание", bg="#091735", fg="#a9badc",
                 font=("DejaVu Sans", 9, "bold")).pack(anchor="w", pady=(8, 2))
        description = tk.Text(form, height=5, bg="#102044", fg="white",
                              insertbackground="white", relief="flat", wrap="word")
        description.pack(fill="both", expand=True)
        description.insert("1.0", (existing or {}).get("description", ""))

        def save():
            payload = {key: var.get().strip() for key, var in values.items()}
            payload["description"] = description.get("1.0", "end-1c").strip()
            try:
                if existing:
                    client.update_listing(str(existing["id"]), payload)
                else:
                    client.create_listing(payload)
            except (CloudMarketplaceError, ValueError) as exc:
                notify_error(exc)
                return
            dialog.destroy()
            refresh()
        tk.Button(form, text="СОХРАНИТЬ", command=save, bg="#6330b4", fg="white",
                  activebackground="#8549df", relief="flat", padx=18, pady=8).pack(
                      side="right", pady=(10, 0))

    def respond():
        item = selected()
        if not item:
            messagebox.showinfo("Отклик", "Выберите объявление.", parent=win)
            return
        if not client.is_authenticated:
            messagebox.showinfo("Отклик", "Войдите в аккаунт, чтобы отправить отклик.", parent=win)
            return
        if item.get("owner_id") == client.session.user.get("id"):
            messagebox.showinfo("Отклик", "Нельзя откликнуться на собственное объявление.", parent=win)
            return
        message = simpledialog.askstring("Отклик на объявление",
            "Напишите сообщение автору (до 2000 символов):", parent=win)
        if message is None:
            return
        try:
            client.respond_to_listing(str(item["id"]), message)
            messagebox.showinfo("Отклик отправлен", "Ваш отклик сохранён в общей Бирже.", parent=win)
        except (CloudMarketplaceError, ValueError) as exc:
            notify_error(exc)

    def open_inbox():
        if not client.is_authenticated:
            messagebox.showinfo("Входящие отклики", "Сначала войдите в аккаунт.", parent=win)
            return
        inbox = tk.Toplevel(win)
        inbox.title("Vkus — Входящие отклики")
        inbox.configure(bg="#07122a")
        inbox.geometry("900x570")
        inbox.minsize(720, 440)
        inbox.transient(win)
        tk.Label(inbox, text="ВХОДЯЩИЕ ОТКЛИКИ", bg="#07122a", fg="#d18aff",
                 font=("DejaVu Sans", 15, "bold")).pack(anchor="w", padx=18, pady=(16, 10))
        frame = tk.Frame(inbox, bg="#07122a")
        frame.pack(fill="both", expand=True, padx=18, pady=(0, 10))
        cols = ("listing", "message", "status", "created")
        inbox_table = ttk.Treeview(frame, columns=cols, show="headings",
                                   style="CloudMarket.Treeview")
        for key, title, width in (
            ("listing", "Объявление", 230), ("message", "Сообщение", 390),
            ("status", "Статус", 110), ("created", "Дата", 130),
        ):
            inbox_table.heading(key, text=title)
            inbox_table.column(key, width=width, anchor="w")
        sb = ttk.Scrollbar(frame, orient="vertical", command=inbox_table.yview)
        inbox_table.configure(yscrollcommand=sb.set)
        inbox_table.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        note = tk.Label(inbox, text="Выберите отклик для просмотра полного сообщения.",
                        bg="#0a1731", fg="#9fb4df", anchor="w", justify="left",
                        padx=12, pady=10, wraplength=840)
        note.pack(fill="x", padx=18, pady=(0, 8))
        inbox_rows = {}

        def load_inbox():
            try:
                rows = client.list_incoming_responses(limit=100)
            except (CloudMarketplaceError, ValueError) as exc:
                notify_error(exc)
                return
            inbox_rows.clear()
            inbox_table.delete(*inbox_table.get_children())
            for row in rows:
                key = str(row["id"])
                inbox_rows[key] = row
                listing = row.get("listing") or {}
                created = (row.get("created_at") or "")[:16].replace("T", " ")
                preview = row.get("message", "").replace("\n", " ")
                if len(preview) > 100:
                    preview = preview[:97] + "…"
                inbox_table.insert("", "end", iid=key, values=(
                    listing.get("title") or "Объявление",
                    preview, row.get("status") or "Новый", created,
                ))
            note.configure(text=f"Всего входящих откликов: {len(rows)}")

        def show_incoming(_event=None):
            selection = inbox_table.selection()
            row = inbox_rows.get(selection[0]) if selection else None
            if not row:
                return
            listing = row.get("listing") or {}
            note.configure(text=(
                f"Объявление: {listing.get('title') or '—'}\n"
                f"Сообщение: {row.get('message') or '—'}\n"
                f"Статус: {row.get('status') or 'Новый'}\n"
                f"Дата: {(row.get('created_at') or '')[:19].replace('T', ' ')}"
            ))

        def set_incoming_status(status):
            selection = inbox_table.selection()
            row = inbox_rows.get(selection[0]) if selection else None
            if not row:
                messagebox.showinfo("Отклики", "Сначала выберите отклик.", parent=inbox)
                return
            try:
                client.update_response_status(str(row["id"]), status)
            except (CloudMarketplaceError, ValueError) as exc:
                notify_error(exc)
                return
            load_inbox()

        inbox_table.bind("<<TreeviewSelect>>", show_incoming)
        bar = tk.Frame(inbox, bg="#07122a")
        bar.pack(fill="x", padx=18, pady=(0, 16))
        tk.Label(bar, text="Статус отклика:", bg="#07122a", fg="#8fa5d4",
                 font=("DejaVu Sans", 8)).pack(side="left")
        for caption, status, color in (
            ("Отметить просмотренным", "Просмотрен", "#24539b"),
            ("Принять", "Принят", "#236b59"),
            ("Отклонить", "Отклонён", "#64263f"),
        ):
            tk.Button(bar, text=caption,
                      command=lambda value=status: set_incoming_status(value),
                      bg=color, fg="white", relief="flat", padx=10, pady=7,
                      font=("DejaVu Sans", 8, "bold")).pack(side="right", padx=(6, 0))
        tk.Button(bar, text="Обновить", command=load_inbox, bg="#182b55",
                  fg="white", relief="flat", padx=12, pady=7).pack(side="right", padx=6)
        load_inbox()

    def remove():
        item = selected()
        if not item:
            messagebox.showinfo("Биржа", "Выберите своё объявление.", parent=win)
            return
        if not client.is_authenticated or item.get("owner_id") != client.session.user.get("id"):
            messagebox.showinfo("Биржа", "Изменять можно только собственные объявления.", parent=win)
            return
        if messagebox.askyesno("Удалить объявление", "Удалить объявление из общей Биржи?",
                               parent=win):
            try:
                client.delete_listing(str(item["id"]))
                refresh()
            except CloudMarketplaceError as exc:
                notify_error(exc)

    def edit():
        item = selected()
        if not item:
            messagebox.showinfo("Биржа", "Выберите своё объявление.", parent=win)
        elif not client.is_authenticated or item.get("owner_id") != client.session.user.get("id"):
            messagebox.showinfo("Биржа", "Редактировать можно только собственные объявления.", parent=win)
        else:
            create_or_edit(item)

    def action(caption, command, color="#182b55"):
        tk.Button(actions, text=caption, command=command, bg=color, fg="white",
                  activebackground="#7540c8", activeforeground="white",
                  relief="flat", bd=0, padx=14, pady=9,
                  font=("DejaVu Sans", 9, "bold"), cursor="hand2").pack(
                      side="right", padx=(6, 0))

    action("Отклики", open_inbox, "#1b5c91")
    tk.Button(auth_bar, text="ВОЙТИ", command=sign_in, bg="#24539b", fg="white",
              relief="flat", padx=12, pady=6).pack(side="left", padx=(12, 4))
    tk.Button(auth_bar, text="РЕГИСТРАЦИЯ", command=sign_up, bg="#6330b4", fg="white",
              relief="flat", padx=12, pady=6).pack(side="left", padx=4)
    tk.Button(auth_bar, text="ВЫЙТИ", command=sign_out, bg="#4b2842", fg="white",
              relief="flat", padx=12, pady=6).pack(side="left", padx=4)
    action("Удалить", remove, "#64263f")
    action("Редактировать", edit, "#253b66")
    action("Профиль", edit_profile, "#1b5c91")
    action("↩ Откликнуться", respond, "#1b5c91")
    action("+ Добавить объявление", create_or_edit, "#7136c3")

    # The supplied artwork is the complete UI. Tkinter only paints it and handles
    # pointer input; no visible widgets are placed over or cut out of the image.
    auth_bar.pack_forget()
    gate = tk.Frame(shell, bg="#030817", highlightthickness=0, bd=0)
    gate.place(in_=shell, x=0, y=0, relwidth=1, relheight=1)
    gate_canvas = tk.Canvas(gate, bg="#030817", highlightthickness=0, bd=0)
    gate_canvas.place(relwidth=1, relheight=1)
    gate_image_path = Path(__file__).resolve().parent / "assets" / "marketplace_role_gate.png"
    from PIL import Image, ImageTk
    gate_source = Image.open(gate_image_path).convert("RGB")
    source_width, source_height = gate_source.size
    # Button hit areas are normalized against the source artwork, not screen pixels.
    # They therefore track the image through window resizing, DPI scaling and HDMI displays.
    gate_regions = {
        "left": (276 / source_width, 617 / source_height,
                 772 / source_width, 709 / source_height),
        "right": (862 / source_width, 617 / source_height,
                  1363 / source_width, 709 / source_height),
    }
    gate_transform = {"scale": 1.0, "x": 0.0, "y": 0.0, "width": source_width,
                      "height": source_height}
    gate_canvas._photo = None

    def redraw_role_gate(_event=None):
        cw, ch = max(1, gate_canvas.winfo_width()), max(1, gate_canvas.winfo_height())
        # Keep the entire reference visible; letterbox space is not clickable.
        scale = min(cw / source_width, ch / source_height)
        iw = max(1, round(source_width * scale))
        ih = max(1, round(source_height * scale))
        resized = gate_source.resize((iw, ih), Image.Resampling.LANCZOS)
        gate_canvas._photo = ImageTk.PhotoImage(resized)
        gate_canvas.delete("all")
        ox, oy = (cw - iw) / 2, (ch - ih) / 2
        gate_canvas.create_image(ox, oy, image=gate_canvas._photo, anchor="nw")
        gate_transform.update(scale=scale, x=ox, y=oy, width=iw, height=ih)

    def role_at_canvas_point(x, y):
        transform = gate_transform
        scale = transform["scale"]
        image_x = (x - transform["x"]) / scale
        image_y = (y - transform["y"]) / scale
        if not (0 <= image_x < source_width and 0 <= image_y < source_height):
            return None
        nx, ny = image_x / source_width, image_y / source_height
        for key, bounds in gate_regions.items():
            x1, y1, x2, y2 = bounds
            if x1 <= nx <= x2 and y1 <= ny <= y2:
                return key
        return None
    def finish_gate_auth(panel):
        update_account_label()
        panel.destroy()
        gate.place_forget()
        refresh()

    def show_role_auth(role):
        accent = "#d05aff" if role == "Соискатель" else "#23bfff"
        panel = tk.Frame(gate, bg="#08152f", highlightbackground=accent,
                         highlightthickness=2, padx=30, pady=24)
        panel.place(relx=0.5, rely=0.5, anchor="center", width=500, height=390)
        panel.lift()
        tk.Label(panel, text="VKUS  /  ДОСКА ОБЪЯВЛЕНИЙ", bg="#08152f", fg=accent,
                 font=("DejaVu Sans", 9, "bold")).pack(anchor="w")
        tk.Label(panel, text=("Регистрация соискателя" if role == "Соискатель" else "Регистрация рекламодателя"),
                 bg="#08152f", fg="#f4f0ff", font=("DejaVu Sans", 16, "bold")).pack(anchor="w", pady=(8,18))
        tk.Label(panel, text="EMAIL", bg="#08152f", fg="#91a8d7",
                 font=("DejaVu Sans", 8, "bold")).pack(anchor="w")
        email_entry = tk.Entry(panel, textvariable=email_var, bg="#101f43", fg="#f4f6ff",
                               insertbackground="white", relief="flat", bd=0,
                               highlightthickness=1, highlightbackground="#344d82")
        email_entry.pack(fill="x", ipady=9, pady=(4,12))
        tk.Label(panel, text="ПАРОЛЬ  ·  НЕ МЕНЕЕ 8 СИМВОЛОВ", bg="#08152f", fg="#91a8d7",
                 font=("DejaVu Sans", 8, "bold")).pack(anchor="w")
        password_entry = tk.Entry(panel, textvariable=password_var, show="•", bg="#101f43",
                                  fg="#f4f6ff", insertbackground="white", relief="flat", bd=0,
                                  highlightthickness=1, highlightbackground="#344d82")
        password_entry.pack(fill="x", ipady=9, pady=(4,16))

        def register_role():
            try:
                client.sign_up(email_var.get(), password_var.get(), role=role)
                if client.is_authenticated:
                    finish_gate_auth(panel)
                else:
                    messagebox.showinfo("Подтверждение email",
                        "Аккаунт создан. Подтвердите email по ссылке из письма, затем войдите.", parent=panel)
            except (CloudMarketplaceError, ValueError) as exc:
                notify_error(exc)

        def login_role():
            try:
                client.sign_in(email_var.get(), password_var.get())
                saved_role = (client.session.user.get("user_metadata") or {}).get("marketplace_role")
                if saved_role not in ("Соискатель", "Рекламодатель"):
                    client.set_marketplace_role(role)
                elif saved_role != role:
                    messagebox.showinfo("Роль аккаунта",
                        f"У аккаунта уже сохранена роль: {saved_role}. Выберите соответствующую карточку.", parent=panel)
                    return
                finish_gate_auth(panel)
            except (CloudMarketplaceError, ValueError) as exc:
                notify_error(exc)

        tk.Button(panel, text="ЗАРЕГИСТРИРОВАТЬСЯ", command=register_role,
                  bg="#7136b9" if role == "Соискатель" else "#087eb7", fg="white",
                  activebackground=accent, relief="flat", bd=0, pady=10,
                  font=("DejaVu Sans", 9, "bold")).pack(fill="x")
        tk.Button(panel, text="УЖЕ ЕСТЬ АККАУНТ · ВОЙТИ", command=login_role,
                  bg="#142b4c", fg="#d4f7ff", activebackground="#24539b",
                  relief="flat", bd=0, pady=8, font=("DejaVu Sans", 8, "bold")).pack(fill="x", pady=(8,0))
        tk.Button(panel, text="← НАЗАД К ВЫБОРУ РОЛИ", command=panel.destroy,
                  bg="#0b1c38", fg="#a8c8ff", activebackground="#17345d",
                  relief="flat", bd=0, pady=7, font=("DejaVu Sans", 8, "bold")).pack(fill="x", pady=(8,0))
        email_entry.focus_set()
    def handle_role_gate_click(event):
        key = role_at_canvas_point(event.x, event.y)
        role = {"left": "Соискатель", "right": "Рекламодатель"}.get(key)
        if role:
            show_role_auth(role)
            return "break"

    gate_canvas.bind("<Configure>", redraw_role_gate)
    gate_canvas.bind("<Button-1>", handle_role_gate_click)
    def update_gate_cursor(event):
        gate_canvas.configure(cursor="hand2" if role_at_canvas_point(event.x, event.y) else "")
    gate_canvas.bind("<Motion>", update_gate_cursor)
    gate._canvas, gate._hit_regions = gate_canvas, gate_regions
    win._marketplace_gate_canvas, win._marketplace_gate_layout = gate_canvas, gate_regions
    # Stable handles for the repository's UI smoke test; normal users interact
    # with the same visible controls and callbacks.
    win._marketplace_search_entry = query_entry
    win._marketplace_reset_button = reset_button
    win._marketplace_filters_panel = filters_shell
    win._marketplace_cards_frame = cards_frame
    win._marketplace_refresh = refresh
    win._marketplace_gate = gate
    if client.is_authenticated:
        saved_role = (client.session.user.get("user_metadata") or {}).get("marketplace_role")
        if saved_role in ("Соискатель", "Рекламодатель"):
            gate.place_forget()
        else:
            update_account_label()
    gate.lift()
    for variable in (query_var, kind_var, category_var, city_var):
        variable.trace_add("write", refresh)
    refresh()
    return win
