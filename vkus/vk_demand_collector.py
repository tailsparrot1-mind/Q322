"""Collect public VK search results and send reviewed candidates to Vkus Demand Engine.

Uses the existing Vkus BrowserManager/Firefox profile. It does not bypass VK access
controls, access private content, send messages, or automate account actions.
Uploads are opt-in via --upload; otherwise records are printed for review.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from vkus.browser import BrowserManager


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
    """Conservative rules: ambiguous/weak signals remain unknown."""
    value = re.sub(r"\s+", " ", str(text or "").lower()).strip()
    request = any(re.search(p, value, re.I) for p in REQUEST_PATTERNS)
    offer = any(re.search(p, value, re.I) for p in OFFER_PATTERNS)
    if request and not offer:
        return "request", 0.78
    if offer and not request:
        return "offer", 0.78
    return "unknown", 0.0


def _stable_key(item: dict[str, Any]) -> str:
    source = str(item.get("url") or "").strip()
    body = re.sub(r"\s+", " ", str(item.get("comment_text") or item.get("text") or "")).strip().lower()
    kind = "comment" if item.get("kind") == "comments" else "post"
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
        "source_kind": "comment" if item.get("kind") == "comments" else "post",
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
    parser = argparse.ArgumentParser(description="Vkus VK public-demand collector")
    parser.add_argument("--query", action="append", required=True, help="VK search phrase; repeat to add phrases")
    parser.add_argument("--mode", choices=("posts", "comments"), default="posts")
    parser.add_argument("--city", default="")
    parser.add_argument("--region", default="")
    parser.add_argument("--limit", type=int, default=30, help="maximum results per query")
    parser.add_argument("--upload", action="store_true", help="send results to Vkus; default is review-only dry run")
    parser.add_argument("--json-out", default="", help="optional path for a local JSON review file")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.limit < 1 or args.limit > 100:
        print("ERROR: --limit must be between 1 and 100", file=sys.stderr)
        return 2

    logger = logging.getLogger("vkus.vk_demand_collector")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    browser = BrowserManager(logger)
    normalized: dict[str, dict[str, Any]] = {}
    try:
        for query in args.query:
            logger.info("Searching public VK %s for: %s", args.mode, query)
            results = browser.search_vk(
                query=query,
                city=args.city,
                region=args.region,
                mode=args.mode,
                limit=args.limit,
            )
            for result in results:
                record = normalize_result(result, city=args.city, region=args.region)
                if record:
                    normalized[record["external_key"]] = record
    except Exception as exc:
        logger.exception("VK collection failed")
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        # Vkus may already own this persistent Firefox session. Detach the
        # collector's atexit handler instead of quitting the shared browser.
        import atexit
        try:
            atexit.unregister(browser.stop)
        except Exception:
            pass

    records = list(normalized.values())
    print(json.dumps({"collected": len(records), "items": records}, ensure_ascii=False, indent=2))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump({"collected": len(records), "items": records}, handle, ensure_ascii=False, indent=2)

    if not args.upload:
        print("DRY RUN: nothing was uploaded. Inspect results, then rerun with --upload.", file=sys.stderr)
        return 0
    if not records:
        print("No eligible public results; upload skipped.", file=sys.stderr)
        return 0

    endpoint = os.environ.get("VKUS_SUPABASE_URL", "").strip()
    source_id = os.environ.get("VKUS_SOURCE_ID", "").strip()
    token = os.environ.get("VKUS_COLLECTOR_TOKEN", "").strip()
    if not endpoint or not source_id or not token:
        print("ERROR: set VKUS_SUPABASE_URL, VKUS_SOURCE_ID and VKUS_COLLECTOR_TOKEN", file=sys.stderr)
        return 2

    try:
        outcomes = []
        for start in range(0, len(records), 100):
            outcomes.append(upload_batch(endpoint, source_id, token, records[start:start + 100]))
        print(json.dumps({"upload_results": outcomes}, ensure_ascii=False, indent=2))
        return 0 if all(x.get("status") == "success" for x in outcomes) else 1
    except Exception as exc:
        logger.exception("Upload failed")
        print(f"UPLOAD ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
