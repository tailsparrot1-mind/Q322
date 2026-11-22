"""Normalize user-selected VK public posts/comments for the Vkus demand engine.

This module intentionally does not automate VK page collection. VK terms may
restrict automated collection and commercial reuse; use only data supplied by
the user under an approved collection basis. Backend upload remains disabled
until the VK source has been terms-reviewed and enabled.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REQUEST_PATTERNS = (
    r"\bищу\s+(?:мастера|специалиста|исполнителя|ремонтника|сантехника|электрика)\b",
    r"\bнужен\s+(?:мастер|специалист|исполнитель|ремонт|сантехник|электрик)\b",
    r"\bнужна\s+(?:помощь|услуга|ремонт|замена|установка)\b",
    r"\bищем\s+(?:мастера|специалиста|исполнителя)\b",
    r"\bкто\s+(?:может|посоветует|знает)\b",
    r"\bпосоветуйте\s+(?:мастера|специалиста|компанию|сервис)\b",
    r"\bподскажите\s+(?:мастера|специалиста|кого)\b",
    r"\bтребуется\s+(?:мастер|специалист|ремонт|услуга)\b",
    r"\bищу\s+(?:компанию|фирму|подрядчика)\b",
)
OFFER_PATTERNS = (
    r"\bпредлагаю\s+(?:услуги|свои услуги|работы)\b",
    r"\bоказываю\s+(?:услуги|помощь)\b",
    r"\bвыполняю\s+(?:работы|ремонт|заказы)\b",
    r"\bуслуги\s+(?:мастера|электрика|сантехника|ремонта)\b",
    r"\bмастер\s+на\s+час\b",
    r"\bготов\s+взять\s+заказ\b",
)


def classify_intent(text: str) -> tuple[str, float]:
    """Conservative rules; heuristic matches remain below backend auto-activation threshold."""
    value = re.sub(r"\s+", " ", str(text or "").lower()).strip()
    request = any(re.search(p, value, re.I) for p in REQUEST_PATTERNS)
    offer = any(re.search(p, value, re.I) for p in OFFER_PATTERNS)
    if request and not offer:
        return "request", 0.68
    if offer and not request:
        return "offer", 0.68
    return "unknown", 0.0


def _stable_key(item: dict[str, Any]) -> str:
    source = str(item.get("url") or "").strip()
    body = re.sub(r"\s+", " ", str(item.get("comment_text") or item.get("text") or "")).strip().lower()
    kind = "comment" if item.get("kind") in ("comment", "comments") else "post"
    raw = f"vk|{kind}|{source}|{body}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _title(body: str) -> str:
    text = re.sub(r"\s+", " ", body).strip()
    if not text:
        return "Публикация VK"
    first = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0]
    first = first[:177].rstrip()
    return first + ("..." if len(text) > 177 else "")


def normalize_result(item: dict[str, Any], city: str = "", region: str = "") -> dict[str, Any] | None:
    body = re.sub(r"\s+", " ", str(item.get("comment_text") or item.get("text") or "")).strip()
    url = str(item.get("url") or "").strip()
    if len(body) < 3 or not url.startswith(("https://vk.ru/", "https://vk.com/")):
        return None
    intent, confidence = classify_intent(body)
    date_ts = item.get("date_ts")
    published_at = None
    try:
        ts = float(date_ts or 0)
        if ts > 0:
            published_at = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        pass
    return {
        "external_key": _stable_key(item),
        "source_kind": "comment" if item.get("kind") in ("comment", "comments") else "post",
        "intent": intent,
        "category": None,
        "title": _title(body),
        "body_excerpt": body[:5000],
        "author_label": str(item.get("author_name") or item.get("username") or "")[:160] or None,
        "region": region.strip() or None,
        "city": city.strip() or None,
        "language_code": "ru",
        "source_url": url,
        "published_at": published_at,
        "intent_confidence": confidence,
    }


def load_user_selected_items(path: str) -> list[dict[str, Any]]:
    """Read only an explicit user-prepared JSON export; never fetch VK pages."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError("Input JSON must be an array or an object containing an 'items' array")
    if len(items) > 1000:
        raise ValueError("A local import file cannot contain more than 1000 items")
    if not all(isinstance(item, dict) for item in items):
        raise ValueError("Every input item must be a JSON object")
    return items


def upload_batch(endpoint: str, source_id: str, token: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    payload = json.dumps({"source_id": source_id, "items": items}, ensure_ascii=False).encode("utf-8")
    request = Request(
        endpoint.rstrip("/") + "/functions/v1/ingest-vkus-demand",
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=45) as response:
            raw = response.read().decode("utf-8", errors="replace")
            result = json.loads(raw) if raw else {}
            if response.status >= 400:
                raise RuntimeError(f"Ingestion HTTP {response.status}: {raw[:800]}")
            return result if isinstance(result, dict) else {"result": result}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ingestion HTTP {exc.code}: {detail[:800]}") from exc
    except URLError as exc:
        raise RuntimeError(f"Cannot reach Vkus ingestion endpoint: {exc.reason}") from exc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Vkus VK user-selected content importer")
    parser.add_argument("--input-json", required=True, help="JSON file with user-selected VK posts/comments")
    parser.add_argument("--city", default="")
    parser.add_argument("--region", default="")
    parser.add_argument("--upload", action="store_true", help="send normalized records; default is review-only")
    parser.add_argument("--json-out", default="", help="optional path for normalized JSON review output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        raw_items = load_user_selected_items(args.input_json)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"INPUT ERROR: {exc}", file=sys.stderr)
        return 2

    records: dict[str, dict[str, Any]] = {}
    rejected = 0
    for item in raw_items:
        record = normalize_result(item, city=args.city, region=args.region)
        if record:
            records[record["external_key"]] = record
        else:
            rejected += 1

    normalized = list(records.values())
    output = {"imported": len(normalized), "rejected": rejected, "items": normalized}
    rendered = json.dumps(output, ensure_ascii=False, indent=2)
    print(rendered)
    if args.json_out:
        Path(args.json_out).write_text(rendered + "\n", encoding="utf-8")

    if not args.upload:
        print("REVIEW ONLY: nothing was uploaded. Inspect the normalized records first.", file=sys.stderr)
        return 0
    if not normalized:
        print("No eligible records; upload skipped.", file=sys.stderr)
        return 0

    endpoint = os.environ.get("VKUS_SUPABASE_URL", "").strip()
    source_id = os.environ.get("VKUS_SOURCE_ID", "").strip()
    token = os.environ.get("VKUS_COLLECTOR_TOKEN", "").strip()
    if not endpoint or not source_id or not token:
        print("ERROR: set VKUS_SUPABASE_URL, VKUS_SOURCE_ID and VKUS_COLLECTOR_TOKEN", file=sys.stderr)
        return 2

    try:
        outcomes = []
        for start in range(0, len(normalized), 100):
            outcomes.append(upload_batch(endpoint, source_id, token, normalized[start:start + 100]))
        print(json.dumps({"upload_results": outcomes}, ensure_ascii=False, indent=2))
        return 0 if all(x.get("status") == "success" for x in outcomes) else 1
    except Exception as exc:
        print(f"UPLOAD ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
