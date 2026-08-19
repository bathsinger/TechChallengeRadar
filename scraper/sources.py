"""
Fetchers. Every function returns a list of raw item dicts:
    {"title": str, "link": str, "summary": str, "published": str, "source": str, "region": str}

Every fetcher is defensive: on any error it prints a warning and returns []
rather than raising, so one broken source never kills the whole daily run.
"""

import re
import urllib.parse

import feedparser
import requests

HEADERS = {
    "User-Agent": "TechChallengeRadar/1.0 (+https://github.com/; personal non-commercial project)"
}
TIMEOUT = 20

_LINK_RE = re.compile(r'href="([^"]+)"')


def _best_link(entry) -> tuple[str, str]:
    """Some feeds (e.g. DARPA) point every <link> at the same generic listing
    page and bury the actual item URL inside the HTML description instead.
    Prefer a link found in the description when it differs from the feed's
    top-level link; fall back to the feed link; keep the guid separately for
    dedup so items are never silently collapsed into one another."""
    feed_link = (entry.get("link", "") or "").strip()
    desc = entry.get("summary", "") or entry.get("description", "") or ""
    match = _LINK_RE.search(desc)
    embedded = match.group(1).strip() if match else ""
    link = embedded if embedded and embedded != feed_link else feed_link
    guid = (entry.get("id") or entry.get("guid") or feed_link or link).strip()
    return link, guid


def fetch_rss(url: str, source_name: str, region: str = "Unknown") -> list[dict]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
        items = []
        for entry in parsed.entries:
            link, guid = _best_link(entry)
            items.append({
                "title": entry.get("title", "").strip(),
                "link": link,
                "guid": guid,
                "summary": (entry.get("summary", "") or entry.get("description", "")).strip(),
                "published": entry.get("published", "") or entry.get("updated", ""),
                "source": source_name,
                "region": region,
            })
        return items
    except Exception as exc:  # noqa: BLE001
        print(f"[sources] RSS fetch failed for {source_name} ({url}): {exc}")
        return []


def fetch_google_news(query: str, region: str = "Unknown") -> list[dict]:
    """Free, no-key discovery via Google News RSS search."""
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
    return fetch_rss(url, source_name=f"Google News: {query}", region=region)


def fetch_eu_portal(text_query: str) -> list[dict]:
    """Best-effort call to the EU Funding & Tenders Portal public search API.

    This endpoint isn't formally documented for third parties and can change
    without notice — if it fails we just skip it, nothing else depends on it.
    """
    url = "https://api.tech.ec.europa.eu/search-api/prod/rest/search"
    params = {
        "apiKey": "SEDIA",
        "text": text_query,
        "pageSize": 25,
        "pageNumber": 1,
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", []) or data.get("result", {}).get("results", [])
        items = []
        for r in results:
            title = r.get("title") or r.get("metadata", {}).get("title", [""])
            if isinstance(title, list):
                title = title[0] if title else ""
            summary = r.get("summary") or ""
            link = r.get("url") or r.get("metadata", {}).get("url", "")
            link = str(link).strip()
            items.append({
                "title": str(title).strip(),
                "link": link,
                "guid": link,
                "summary": str(summary).strip(),
                "published": "",
                "source": "EU Funding & Tenders Portal",
                "region": "Europe",
            })
        return items
    except Exception as exc:  # noqa: BLE001
        print(f"[sources] EU portal fetch failed for query '{text_query}': {exc}")
        return []
