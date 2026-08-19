import datetime as dt
import json
import os
import re
import sys

import yaml

sys.path.insert(0, os.path.dirname(__file__))
from sources import fetch_rss, fetch_google_news, fetch_eu_portal  # noqa: E402
from classify import classify_item  # noqa: E402

HERE = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(HERE, "sources.yaml")
OUTPUT_PATH = os.path.join(HERE, "..", "docs", "data.json")

# Entries with a known past deadline older than this many days get dropped
# from the site. Entries with no known deadline get dropped once they are
# older than this many days since we first saw them (keeps the list fresh).
MAX_AGE_DAYS = 120


def normalize_url(url: str) -> str:
    return re.sub(r"[?#].*$", "", url or "").strip().lower().rstrip("/")


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def gather_raw_items(config: dict) -> list[dict]:
    items: list[dict] = []

    for src in config.get("rss_sources", []) or []:
        items.extend(fetch_rss(src["url"], src["name"], src.get("region", "Unknown")))

    for query in config.get("gnews_queries", []) or []:
        items.extend(fetch_google_news(query))

    eu_cfg = config.get("eu_portal", {}) or {}
    if eu_cfg.get("enabled"):
        for q in eu_cfg.get("text_queries", []) or []:
            items.extend(fetch_eu_portal(q))

    return items


def dedup_key(it: dict) -> str:
    """guid is the reliable unique id; falls back to the normalized link.
    (Some feeds, e.g. DARPA's, point every <link> at the same listing page,
    so guid is what actually keeps distinct items from colliding.)"""
    return (it.get("guid") or "").strip() or normalize_url(it.get("link", ""))


def dedup(items: list[dict]) -> list[dict]:
    seen_keys = set()
    seen_titles = set()
    out = []
    for it in items:
        k = dedup_key(it)
        t = normalize_title(it.get("title", ""))
        if not k or not t:
            continue
        if k in seen_keys or t in seen_titles:
            continue
        seen_keys.add(k)
        seen_titles.add(t)
        out.append(it)
    return out


def load_existing() -> dict:
    if os.path.exists(OUTPUT_PATH):
        try:
            with open(OUTPUT_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            return {"entries": []}
    return {"entries": []}


def is_stale(entry: dict) -> bool:
    today = dt.date.today()
    deadline = entry.get("deadline") or ""
    if deadline:
        try:
            d = dt.date.fromisoformat(deadline)
            return d < today - dt.timedelta(days=7)
        except ValueError:
            pass
    first_seen = entry.get("first_seen") or ""
    try:
        fs = dt.date.fromisoformat(first_seen)
        return (today - fs).days > MAX_AGE_DAYS
    except ValueError:
        return False


def main() -> None:
    config = load_config()
    print("[main] gathering raw items...")
    raw_items = gather_raw_items(config)
    print(f"[main] {len(raw_items)} raw items before dedup")
    raw_items = dedup(raw_items)
    print(f"[main] {len(raw_items)} raw items after dedup")

    existing = load_existing()
    existing_keys = {e.get("dedup_key") for e in existing.get("entries", []) if e.get("dedup_key")}

    today_str = dt.date.today().isoformat()
    new_entries = []
    classified_count = 0

    for raw in raw_items:
        k = dedup_key(raw)
        if k in existing_keys:
            continue  # already classified in a previous run, keep as-is below
        entry = classify_item(raw)
        classified_count += 1
        if entry is None:
            continue
        entry["url"] = raw.get("link", "")
        entry["dedup_key"] = k
        entry["first_seen"] = today_str
        entry["last_seen"] = today_str
        new_entries.append(entry)

    print(f"[main] classified {classified_count} new items -> {len(new_entries)} kept")

    # carry forward existing entries, refresh last_seen, drop stale ones
    carried = []
    for e in existing.get("entries", []):
        e["last_seen"] = e.get("last_seen", today_str)
        if not is_stale(e):
            carried.append(e)

    all_entries = carried + new_entries

    # sort: entries with a known deadline first (soonest first), then unknown
    def sort_key(e):
        d = e.get("deadline") or ""
        try:
            return (0, dt.date.fromisoformat(d))
        except ValueError:
            return (1, dt.date.max)

    all_entries.sort(key=sort_key)

    output = {
        "last_updated": dt.datetime.utcnow().isoformat() + "Z",
        "entries": all_entries,
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[main] wrote {len(all_entries)} entries to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
