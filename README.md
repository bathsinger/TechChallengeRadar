# Tech Challenge Radar

A free, daily-updating radar for technical prize challenges and competitions
(DARPA, NASA, ESA, XPRIZE, Horizon Europe/EIC, HeroX, challenge.gov, and
whatever else news coverage turns up) aimed at inventors, makers and small
technical teams or startups — **not** student-only competitions.

Runs entirely on GitHub's free tier:
- **GitHub Actions** scans sources once a day, deduplicates, classifies and
  writes `docs/data.json`.
- **GitHub Pages** serves `docs/` as a static site that reads that JSON —
  no server, no database, no hosting cost.
- **AI classification is optional.** Without any secret configured, a free
  keyword heuristic filters and tags items. If you add an `ANTHROPIC_API_KEY`
  repo secret, new items also get run through Claude (Haiku) to extract clean
  structured fields (name, reward, dates, region, eligibility) — a few cents
  a day at most, since only *new* items get classified.

## 1. Push this to your own GitHub repo

```bash
cd tech-challenge-radar
git add -A
git commit -m "Initial commit: tech challenge radar"
git branch -M main
git remote add origin https://github.com/<your-username>/<your-repo>.git
git push -u origin main
```

## 2. Enable GitHub Pages

Repo → **Settings → Pages** → Source: **GitHub Actions**.
(The included workflow deploys to Pages itself — you don't need to pick a branch/folder.)

## 3. (Optional) Enable AI classification

Repo → **Settings → Secrets and variables → Actions → New repository secret**
- Name: `ANTHROPIC_API_KEY`
- Value: an API key from [console.anthropic.com](https://console.anthropic.com)

Without this secret the radar still runs daily for free — entries are just
tagged `"classified_by": "keyword"` instead of `"ai"` and descriptions are
the raw snippet rather than an AI-written summary.

## 4. Run it

- It runs automatically every day at 06:00 UTC.
- To run it right now: repo → **Actions → Daily challenge scan → Run workflow**.
- Your site will be live at `https://<your-username>.github.io/<your-repo>/`.

## How it finds challenges

Two layers, both editable in `scraper/sources.yaml` without touching code:

1. **Official RSS feeds** — currently DARPA's opportunities feed. Add more
   as you find them (ESA, HeroX, EIC newsletters, national agencies, etc.).
2. **Google News RSS discovery** — free, no API key, broad web coverage.
   A list of search queries (e.g. `"robotics competition prize money"`,
   `"ESA challenge competition prize"`) catches announcements from sources
   that don't have a clean feed. This is the main way the radar covers
   "whatever's out there" rather than a fixed list of ten known programs.
3. A best-effort call to the **EU Funding & Tenders Portal** search API for
   Horizon Europe / EIC calls (Europe-focused). This endpoint isn't
   officially documented for third parties and may need occasional fixing
   in `scraper/sources.py::fetch_eu_portal` — it fails silently and doesn't
   block the rest of the scan if it breaks.

Every candidate item is then:
- scored by keyword (topic relevance + prize/competition language, with a
  penalty for "students only" phrasing),
- dropped if it doesn't clear the bar,
- (optionally) sent to Claude for structured extraction,
- deduplicated against everything already in `docs/data.json` so items are
  only classified once, not re-processed (and re-billed) every day,
- and dropped from the site once its deadline is a week past, or — if no
  deadline was ever found — 120 days after first appearing.

## Known limitations (read before relying on this)

- **This is best-effort discovery, not an official registry.** Google News
  RSS and generic scraping will miss things and occasionally include noise.
  Always verify eligibility, dates and reward amounts on the organizer's own
  page before entering anything.
- Keyword-only classification (no `ANTHROPIC_API_KEY`) is decent at
  filtering but won't reliably extract exact reward amounts or dates from
  a short snippet — those fields will often show "Unknown" / blank until
  you enable AI classification.
- The EU portal integration is unverified against the live API contract
  (Anthropic's sandbox couldn't reach `ec.europa.eu` to test it end-to-end);
  treat it as a bonus source, not a load-bearing one.
- Add more official feeds over time in `scraper/sources.yaml` — the more
  precise sources you add, the less the radar depends on news-search noise.

## Local development

```bash
cd scraper
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...   # optional
python main.py
```

This writes `docs/data.json`. Open `docs/index.html` with any static server
(e.g. `python -m http.server` from inside `docs/`) to preview.
