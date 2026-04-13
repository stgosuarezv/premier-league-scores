import os
import httpx
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Premier League Scores")
templates = Jinja2Templates(directory="templates")

API_KEY = os.getenv("FOOTBALL_API_KEY", "YOUR_API_KEY_HERE")
BASE_URL = "https://api.football-data.org/v4"


def format_match(match: dict) -> dict:
    home = match["homeTeam"]["shortName"] or match["homeTeam"]["name"]
    away = match["awayTeam"]["shortName"] or match["awayTeam"]["name"]
    home_crest = match["homeTeam"].get("crest", "")
    away_crest = match["awayTeam"].get("crest", "")
    score = match.get("score", {})
    full_time = score.get("fullTime", {})
    home_score = full_time.get("home")
    away_score = full_time.get("away")
    date = match.get("utcDate", "")[:10]  # YYYY-MM-DD
    matchday = match.get("matchday")
    status = match.get("status", "")
    return {
        "home": home,
        "away": away,
        "home_crest": home_crest,
        "away_crest": away_crest,
        "home_score": home_score,
        "away_score": away_score,
        "date": date,
        "matchday": matchday,
        "status": status,
    }


@app.get("/")
async def index(request: Request):
    match = None
    recent_matches = []
    error = None

    if API_KEY == "YOUR_API_KEY_HERE":
        error = "No API key set. Add your key to the .env file as FOOTBALL_API_KEY."
    else:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{BASE_URL}/competitions/PL/matches",
                    params={"status": "FINISHED"},
                    headers={"X-Auth-Token": API_KEY},
                )
            if resp.status_code == 200:
                matches = resp.json().get("matches", [])
                if matches:
                    last_10 = matches[-10:][::-1]  # most recent first
                    match = format_match(last_10[0])
                    recent_matches = [format_match(m) for m in last_10[1:]]
                else:
                    error = "No finished matches found for this season."
            elif resp.status_code == 403:
                error = "Invalid API key. Check your FOOTBALL_API_KEY in .env."
            else:
                error = f"API returned status {resp.status_code}."
        except httpx.RequestError as exc:
            error = f"Network error: {exc}"

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "match": match, "recent_matches": recent_matches, "error": error},
    )
