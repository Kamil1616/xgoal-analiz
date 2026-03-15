"""
Sofascore API — Fikstür + Takım İstatistik Çekici
"""
import requests
import datetime
from typing import Optional

BASE = "https://api.sofascore.com/api/v1"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Android 14; Mobile; rv:120.0) Gecko/120.0 Firefox/120.0",
    "Referer":    "https://www.sofascore.com/",
    "Accept":     "application/json, text/plain, */*",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Origin":     "https://www.sofascore.com",
}

TIMEOUT = 12


def _get(url: str, params: dict = None) -> Optional[dict]:
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        print(f"[Sofascore] GET hata: {url} → {e}")
    return None


# ────────────────────────────────────────────────────────────────────────────
# FİKSTÜR
# ────────────────────────────────────────────────────────────────────────────

def get_fixtures_by_date(date_str: str) -> list[dict]:
    """
    Verilen tarihteki tüm futbol maçlarını döndürür.
    date_str: 'YYYY-MM-DD'
    """
    url  = f"{BASE}/sport/football/scheduled-events/{date_str}"
    data = _get(url)
    if not data or "events" not in data:
        return []

    matches = []
    for ev in data["events"]:
        try:
            home = ev["homeTeam"]["name"]
            away = ev["awayTeam"]["name"]
            home_id = ev["homeTeam"]["id"]
            away_id = ev["awayTeam"]["id"]
            match_id = ev["id"]

            tournament = ev.get("tournament", {})
            league_name = tournament.get("name", "")
            category = tournament.get("category", {}).get("name", "")
            league_full = f"{category} — {league_name}" if category else league_name

            slug = ev.get("tournament", {}).get("category", {}).get("flag", "")
            status_code = ev.get("status", {}).get("code", 0)

            # Başlamamış maçlar (code 0 = not started)
            timestamp = ev.get("startTimestamp", 0)
            dt = datetime.datetime.utcfromtimestamp(timestamp)
            match_time = dt.strftime("%H:%M")

            matches.append({
                "match_id":   match_id,
                "home_team":  home,
                "away_team":  away,
                "home_id":    home_id,
                "away_id":    away_id,
                "league":     league_full,
                "time":       match_time,
                "status":     status_code,
                "timestamp":  timestamp,
            })
        except (KeyError, TypeError):
            continue

    # Saate göre sırala
    matches.sort(key=lambda x: x["timestamp"])
    return matches


def get_live_fixtures() -> list[dict]:
    """Canlı maçları döndürür."""
    url  = f"{BASE}/sport/football/events/live"
    data = _get(url)
    if not data or "events" not in data:
        return []

    matches = []
    for ev in data["events"]:
        try:
            matches.append({
                "match_id":  ev["id"],
                "home_team": ev["homeTeam"]["name"],
                "away_team": ev["awayTeam"]["name"],
                "home_id":   ev["homeTeam"]["id"],
                "away_id":   ev["awayTeam"]["id"],
                "league":    ev.get("tournament", {}).get("name", ""),
                "time":      ev.get("status", {}).get("description", "Canlı"),
                "status":    ev.get("status", {}).get("code", 6),
                "timestamp": ev.get("startTimestamp", 0),
            })
        except (KeyError, TypeError):
            continue
    return matches


# ────────────────────────────────────────────────────────────────────────────
# TAKIM İSTATİSTİKLERİ
# ────────────────────────────────────────────────────────────────────────────

def _parse_event_stats(event: dict, team_id: int) -> Optional[dict]:
    """Tek bir maç eventinden gol bilgisi çıkarır."""
    try:
        home_id    = event["homeTeam"]["id"]
        home_score = event.get("homeScore", {}).get("current", 0) or 0
        away_score = event.get("awayScore", {}).get("current", 0) or 0

        if team_id == home_id:
            return {"goals_scored": home_score, "goals_conceded": away_score,
                    "is_home": True,
                    "result": "W" if home_score > away_score else ("D" if home_score == away_score else "L")}
        else:
            return {"goals_scored": away_score, "goals_conceded": home_score,
                    "is_home": False,
                    "result": "W" if away_score > home_score else ("D" if home_score == away_score else "L")}
    except (KeyError, TypeError):
        return None


def get_team_last_matches(team_id: int, limit: int = 6) -> list[dict]:
    """Son N genel maç."""
    url  = f"{BASE}/team/{team_id}/events/last/0"
    data = _get(url)
    if not data or "events" not in data:
        return []

    events = data["events"][-limit:]
    results = []
    for ev in events:
        parsed = _parse_event_stats(ev, team_id)
        if parsed:
            results.append(parsed)
    return results


def get_team_home_matches(team_id: int, limit: int = 6) -> list[dict]:
    """Son N iç saha maçı."""
    all_matches = _get_all_last(team_id, pages=3)
    home = [m for m in all_matches if m.get("is_home")]
    return home[-limit:]


def get_team_away_matches(team_id: int, limit: int = 6) -> list[dict]:
    """Son N deplasman maçı."""
    all_matches = _get_all_last(team_id, pages=3)
    away = [m for m in all_matches if not m.get("is_home")]
    return away[-limit:]


def _get_all_last(team_id: int, pages: int = 3) -> list[dict]:
    """Birden fazla sayfa geçmişi toplar."""
    all_events = []
    for page in range(pages):
        url  = f"{BASE}/team/{team_id}/events/last/{page}"
        data = _get(url)
        if not data or "events" not in data:
            break
        for ev in data["events"]:
            parsed = _parse_event_stats(ev, team_id)
            if parsed:
                all_events.append(parsed)
        if not data.get("hasNextPage", False) and page > 0:
            break
    return all_events


# ────────────────────────────────────────────────────────────────────────────
# TAKIM ARAMA
# ────────────────────────────────────────────────────────────────────────────

def search_team(name: str) -> Optional[int]:
    """Takım adından ID bul."""
    url  = f"{BASE}/search/multi/{requests.utils.quote(name)}"
    data = _get(url)
    if not data:
        return None
    for item in data.get("results", []):
        if item.get("type") == "team":
            return item["entity"]["id"]
    return None


# ────────────────────────────────────────────────────────────────────────────
# TOPLU VERİ ÇEKME (bir maç için 4 veri seti)
# ────────────────────────────────────────────────────────────────────────────

def get_match_data(home_id: int, away_id: int) -> dict:
    """
    Ev sahibi ve deplasman için 4 veri setini çeker:
    - home_general, home_venue (iç saha)
    - away_general, away_venue (deplasman)
    """
    home_general = get_team_last_matches(home_id, 6)
    home_venue   = get_team_home_matches(home_id, 6)
    away_general = get_team_last_matches(away_id, 6)
    away_venue   = get_team_away_matches(away_id, 6)

    return {
        "home_general": home_general,
        "home_venue":   home_venue,
        "away_general": away_general,
        "away_venue":   away_venue,
    }
