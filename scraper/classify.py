"""
Classification & extraction for candidate challenge items.

Two layers:

1. Keyword heuristic (always runs, free, no API key):
   - scores each item for topic relevance and "this looks like a funded
     challenge/competition" signal
   - flags likely student-only competitions so they can be dropped
   - drops items below a relevance threshold before we ever spend an AI call

2. Optional AI classification (only runs if ANTHROPIC_API_KEY is set as a
   repo secret): asks Claude to read the title/summary/page text and return
   strict JSON with the fields we want to show on the site (name, short
   description, reward, dates, region, individual/team/startup eligibility,
   student-only flag). This is what turns messy news snippets into clean
   structured cards. It's cheap (Haiku, short prompts, a few dozen items/day)
   but it does cost a few cents — that's why it's optional.
"""

import json
import os
import re

TOPIC_KEYWORDS = [
    "robot", "robotics", "hardware", "automation", "automat", "autonomous",
    "engineering", "sensor", "manufactur", "space", "satellite", "aerospace",
    "medic", "medtech", "biotech", "3d print", "additive manufactur",
    "drone", "uav", "embedded", "iot", "electronics", "prototype",
    "invent", "mechatronics", "materials science", "energy technology",
]

PRIZE_KEYWORDS = [
    "prize", "reward", "award", "$", "€", "eur", "usd", "funding",
    "grant", "cash prize", "winner", "competition", "challenge",
    "purse", "million", "thousand",
]

STUDENT_ONLY_KEYWORDS = [
    "high school students only", "university students only",
    "undergraduate students only", "must be enrolled", "student teams only",
    "open only to students", "collegiate", "for students aged",
]

# Phrases that suggest anyone (individual/team/startup/company) can enter —
# used as a mild positive signal, not a hard filter, since many pages don't
# state eligibility in the snippet we have.
OPEN_ENTRY_KEYWORDS = [
    "individuals, teams", "teams and individuals", "startups", "small business",
    "open to anyone", "any team", "companies and individuals", "innovators",
]


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def keyword_score(item: dict) -> dict:
    """Cheap heuristic pass. Mutates nothing; returns score info."""
    text = f"{item.get('title','')} {item.get('summary','')}".lower()

    topic_hits = sum(1 for kw in TOPIC_KEYWORDS if kw in text)
    prize_hits = sum(1 for kw in PRIZE_KEYWORDS if kw in text)
    student_only = any(kw in text for kw in STUDENT_ONLY_KEYWORDS)
    open_entry_hit = any(kw in text for kw in OPEN_ENTRY_KEYWORDS)

    score = topic_hits * 2 + prize_hits + (1 if open_entry_hit else 0)
    if student_only:
        score -= 10

    return {
        "score": score,
        "topic_hits": topic_hits,
        "prize_hits": prize_hits,
        "student_only_guess": student_only,
    }


def passes_keyword_filter(item: dict, min_score: int = 3) -> bool:
    info = keyword_score(item)
    return info["score"] >= min_score and not info["student_only_guess"]


TOPIC_TAGS = {
    "robotics": ["robot"],
    "hardware": ["hardware", "electronics", "embedded"],
    "automation": ["automat"],
    "autonomous": ["autonomous", "uav", "drone"],
    "engineering": ["engineering", "mechatronics"],
    "sensors": ["sensor", "iot"],
    "manufacturing": ["manufactur", "additive manufactur", "3d print"],
    "space": ["space", "satellite", "aerospace"],
    "medicine": ["medic", "medtech", "biotech"],
    "3d-print": ["3d print"],
}


def compute_topics(item: dict) -> list:
    text = f"{item.get('title','')} {item.get('summary','')}".lower()
    return [tag for tag, kws in TOPIC_TAGS.items() if any(kw in text for kw in kws)]


# ---------------------------------------------------------------------------
# Optional AI classification
# ---------------------------------------------------------------------------

AI_SYSTEM_PROMPT = """You screen news items for a "technical challenge radar" \
aimed at inventors, makers, and small technical teams/startups (NOT students-only \
competitions). Given a title and snippet about a possible prize competition, \
technical challenge, or innovation call (e.g. DARPA, NASA, ESA, XPRIZE, Horizon \
Europe / EIC, HeroX, Innocentive, challenge.gov, or similar), decide if it is a \
genuine, currently relevant technical challenge/competition that individuals, \
teams, or startups (not only enrolled students, not only large established \
contractors) could realistically enter.

Respond with ONLY compact JSON, no prose, matching exactly this schema:
{
  "is_relevant": boolean,          // true only if it's a real challenge/prize/competition open to indie teams/startups, on topics like robotics/hardware/automation/autonomous systems/engineering/sensors/manufacturing/space/medicine/3D printing/similar deep-tech
  "is_student_only": boolean,      // true if restricted to enrolled students only
  "name": string,                  // short official-sounding challenge name
  "short_description": string,     // 1-2 plain sentences, in English
  "reward": string,                // e.g. "$2,000,000" or "Unknown" if not stated
  "start_date": string,            // ISO yyyy-mm-dd or "" if unknown
  "deadline": string,              // ISO yyyy-mm-dd or "" if unknown
  "region": string,                // e.g. "Europe", "US", "Global"
  "organizer": string
}
If you are not confident this snippet describes a real, enterable challenge, set is_relevant to false and leave other fields as best guesses."""


def ai_classify(item: dict, api_key: str, model: str = "claude-haiku-4-5") -> dict | None:
    """Call the Anthropic API to classify + extract structured fields.

    Returns a dict (parsed JSON) or None on any failure — callers must treat
    None as "AI classification unavailable, fall back to keyword result".
    """
    try:
        import anthropic
    except ImportError:
        return None

    try:
        client = anthropic.Anthropic(api_key=api_key)
        user_content = (
            f"Title: {item.get('title','')}\n"
            f"Snippet: {item.get('summary','')}\n"
            f"URL: {item.get('link','')}\n"
            f"Source: {item.get('source','')}"
        )
        resp = client.messages.create(
            model=model,
            max_tokens=500,
            system=AI_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        text = "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        )
        text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
        data = json.loads(text)
        return data
    except Exception as exc:  # noqa: BLE001 - we never want this to kill the run
        print(f"[classify] AI classification failed for {item.get('link')}: {exc}")
        return None


def classify_item(item: dict) -> dict | None:
    """Full pipeline for one raw item -> structured entry dict, or None to drop it."""
    kw = keyword_score(item)
    if not passes_keyword_filter(item):
        return None

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    ai_result = ai_classify(item, api_key) if api_key else None

    topics = compute_topics(item)

    if ai_result is not None:
        if not ai_result.get("is_relevant") or ai_result.get("is_student_only"):
            return None
        return {
            "name": ai_result.get("name") or item.get("title", "")[:120],
            "short_description": ai_result.get("short_description", ""),
            "reward": ai_result.get("reward") or "Unknown",
            "start_date": ai_result.get("start_date") or "",
            "deadline": ai_result.get("deadline") or "",
            "region": ai_result.get("region") or "Unknown",
            "organizer": ai_result.get("organizer") or item.get("source", ""),
            "url": item.get("link", ""),
            "topics": topics,
            "classified_by": "ai",
        }

    # Fallback: keyword-only structured entry (less clean, but free & works
    # with zero configuration).
    return {
        "name": item.get("title", "")[:120],
        "short_description": _strip_html(item.get("summary", ""))[:300],
        "reward": "Unknown",
        "start_date": "",
        "deadline": "",
        "region": item.get("region", "Unknown"),
        "organizer": item.get("source", ""),
        "url": item.get("link", ""),
        "topics": topics,
        "classified_by": "keyword",
    }
