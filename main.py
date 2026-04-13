import os
import httpx
from collections import defaultdict
from datetime import datetime, timezone
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Football Scores")
templates = Jinja2Templates(directory="templates")

def _fmt_date(date_str: str) -> str:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%a %d %b")
    except Exception:
        return date_str

templates.env.filters["fmt_date"] = _fmt_date

API_KEY = os.getenv("FOOTBALL_API_KEY", "YOUR_API_KEY_HERE")
BASE_URL = "https://api.football-data.org/v4"

LEAGUES = [
    {"code": "PL",  "name": "Premier League",   "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿"},
    {"code": "ELC", "name": "Championship",      "flag": "🏴󠁧󠁢󠁥󠁮󠁧󠁿"},
    {"code": "PD",  "name": "La Liga",           "flag": "🇪🇸"},
    {"code": "SA",  "name": "Serie A",           "flag": "🇮🇹"},
    {"code": "BL1", "name": "Bundesliga",        "flag": "🇩🇪"},
    {"code": "FL1", "name": "Ligue 1",           "flag": "🇫🇷"},
    {"code": "DED", "name": "Eredivisie",        "flag": "🇳🇱"},
    {"code": "PPL", "name": "Primeira Liga",     "flag": "🇵🇹"},
    {"code": "BSA", "name": "Brasileirão",       "flag": "🇧🇷"},
    {"code": "CL",  "name": "Champions League",  "flag": "🏆"},
    {"code": "CLI", "name": "Libertadores",      "flag": "🌎"},
    {"code": "EC",  "name": "Euro",              "flag": "🇪🇺"},
    {"code": "WC",  "name": "World Cup",         "flag": "🌍"},
]


def format_match(match: dict) -> dict:
    home = match["homeTeam"].get("shortName") or match["homeTeam"]["name"]
    away = match["awayTeam"].get("shortName") or match["awayTeam"]["name"]
    home_crest = match["homeTeam"].get("crest", "")
    away_crest = match["awayTeam"].get("crest", "")
    score = match.get("score", {})
    full_time = score.get("fullTime", {})
    home_score = full_time.get("home")
    away_score = full_time.get("away")
    utc_date = match.get("utcDate", "")
    date_str = utc_date[:10]
    time_str = utc_date[11:16] if len(utc_date) >= 16 else ""
    matchday = match.get("matchday")
    status = match.get("status", "")
    return {
        "home": home,
        "away": away,
        "home_crest": home_crest,
        "away_crest": away_crest,
        "home_score": home_score,
        "away_score": away_score,
        "date": date_str,
        "time": time_str,
        "utc_datetime": utc_date,  # full ISO string for client-side tz conversion
        "matchday": matchday,
        "status": status,
    }


async def fetch_league_data(league: str) -> dict:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    grouped = []
    next_upcoming_date = None
    error = None
    not_available = False

    if API_KEY == "YOUR_API_KEY_HERE":
        error = "No API key set. Add your key to the .env file as FOOTBALL_API_KEY."
        return dict(grouped=grouped, next_upcoming_date=next_upcoming_date,
                    error=error, not_available=not_available)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{BASE_URL}/competitions/{league}/matches",
                headers={"X-Auth-Token": API_KEY},
            )
        if resp.status_code == 200:
            matches = resp.json().get("matches", [])
            date_map: dict[str, list] = defaultdict(list)
            for m in matches:
                fmt = format_match(m)
                date_map[fmt["date"]].append(fmt)

            # Find the first date that has any non-finished match (could be today).
            upcoming_statuses = {"SCHEDULED", "TIMED", "IN_PLAY", "PAUSED"}
            next_upcoming_date = None
            for d in sorted(date_map.keys()):
                if any(m["status"] in upcoming_statuses for m in date_map[d]):
                    next_upcoming_date = d
                    break

            # Dates on/after next_upcoming_date → future section (far-future first).
            # Dates before next_upcoming_date → past section (most-recent first).
            if next_upcoming_date:
                future_desc = sorted((d for d in date_map if d >= next_upcoming_date), reverse=True)
                past_desc   = sorted((d for d in date_map if d < next_upcoming_date),  reverse=True)
            else:
                future_desc = []
                past_desc   = sorted(date_map.keys(), reverse=True)

            for d in future_desc + past_desc:
                day_matches = date_map[d]
                matchday = day_matches[0]["matchday"]
                grouped.append((d, matchday, day_matches))

        elif resp.status_code == 403:
            error = "Invalid API key. Check your FOOTBALL_API_KEY in .env."
        elif resp.status_code in (400, 404):
            not_available = True
        else:
            error = f"API error: {resp.status_code}"
    except httpx.RequestError as exc:
        error = f"Network error: {exc}"

    return dict(grouped=grouped, next_upcoming_date=next_upcoming_date,
                error=error, not_available=not_available)


@app.get("/")
async def index(request: Request, league: str = "PL"):
    data = await fetch_league_data(league)
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "leagues": LEAGUES, "active_league": league, **data},
    )


@app.get("/matches-partial")
async def matches_partial(request: Request, league: str = "PL"):
    data = await fetch_league_data(league)
    return templates.TemplateResponse("_matches.html", {"request": request, **data})
