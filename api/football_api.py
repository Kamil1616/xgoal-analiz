import os
import requests
from datetime import datetime, timedelta
import time

# ─── API KEYS ─────────────────────────────────────────────────────────────────
AS_KEY = os.environ.get("ALLSPORTS_KEY", "")
AS_URL = "https://apiv2.allsportsapi.com/football"

LIG_ORT = 1.35

SOFA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Android 11; Mobile; rv:109.0) Gecko/109.0 Firefox/109.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Referer": "https://www.sofascore.com/",
    "Origin": "https://www.sofascore.com",
    "Cache-Control": "no-cache",
}
SOFA_URL = "https://api.sofascore.com/api/v1"

# ─── DEFAULT STATS ────────────────────────────────────────────────────────────
def default_stats():
    return {
        "home_attack": 1.0, "home_defence": 1.0,
        "away_attack": 1.0, "away_defence": 1.0,
        "general": {
            "avg_scored": 1.35, "goals_scored": 27, "goals_conceded": 20,
            "btts_rate": 0.45, "ht_goal_ratio": 0.27, "tempo_score": 2.5
        },
        "home": {"avg_scored": 1.5, "goals_scored": 15, "goals_conceded": 10},
        "away": {"avg_scored": 1.1, "goals_scored": 12, "goals_conceded": 14}
    }

def cap_att(v): return max(0.3, min(2.5, v))
def cap_def(v): return max(0.4, min(2.5, v))

# ─── SOFASCORE: FIXTURES ──────────────────────────────────────────────────────
def get_fixtures_sofascore(date):
    """Sofascore'dan günlük fikstür çek (UTC+3 için önceki gün de dahil)"""
    try:
        # Türkiye UTC+3 — önceki günün geç maçları da bu tarihte olabilir
        prev_date = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
        all_events = []
        for d in [prev_date, date]:
            r = requests.get(
                f"{SOFA_URL}/sport/football/scheduled-events/{d}",
                headers=SOFA_HEADERS, timeout=15
            )
            if r.status_code == 200:
                all_events.extend(r.json().get("events", []))

        # Sadece istenen tarihe ait maçları filtrele (UTC+3)
        target = datetime.strptime(date, "%Y-%m-%d")
        filtered = []
        for e in all_events:
            ts = e.get("startTimestamp", 0)
            local_dt = datetime.utcfromtimestamp(ts + 10800)  # UTC+3
            if local_dt.strftime("%Y-%m-%d") == date:
                filtered.append(e)
        events = filtered
        result = []
        for e in events:
            home = e.get("homeTeam", {})
            away = e.get("awayTeam", {})
            tournament = e.get("tournament", {})
            unique_tournament = tournament.get("uniqueTournament", {})
            status = e.get("status", {})
            status_code = status.get("code", 0)
            status_type = status.get("type", "notstarted")

            # Skor
            home_score = e.get("homeScore", {})
            away_score = e.get("awayScore", {})
            home_goals = home_score.get("current")
            away_goals = away_score.get("current")
            home_ht = home_score.get("period1")
            away_ht = away_score.get("period1")

            # Status map
            if status_type == "finished":
                st = "FT"
            elif status_type == "inprogress":
                st = "1H"
            else:
                st = "NS"

            # Saat (UTC+3 Türkiye = +10800 saniye)
            ts = e.get("startTimestamp", 0)
            try:
                local_dt = datetime.utcfromtimestamp(ts + 10800)
                match_time = local_dt.strftime("%Y-%m-%dT%H:%M:%S+03:00")
                local_date = local_dt.strftime("%Y-%m-%d")
            except:
                match_time = f"{date}T00:00:00+03:00"
                local_date = date

            result.append({
                "fixture_id": e.get("id"),
                "date": date,
                "time": match_time,
                "status": st,
                "elapsed": status.get("description"),
                "home_team_id": home.get("id"),
                "home_team_name": home.get("name"),
                "away_team_id": away.get("id"),
                "away_team_name": away.get("name"),
                "home_goals": home_goals,
                "away_goals": away_goals,
                "home_ht_goals": home_ht,
                "away_ht_goals": away_ht,
                "league_id": unique_tournament.get("id"),
                "league_name": tournament.get("name"),
                "country": unique_tournament.get("category", {}).get("name", ""),
                "season": str(datetime.now().year),
            })
        print(f"Sofascore fixtures: {len(result)} maç ({date})")
        return result
    except Exception as e:
        print(f"Sofascore fixtures error: {e}")
        return []

def get_fixtures(date):
    """Ana fixture fonksiyonu: Sofascore → AllSports"""
    fixtures = get_fixtures_sofascore(date)
    if fixtures:
        return fixtures
    # Yedek: AllSports
    return get_fixtures_allsports(date)

# ─── SOFASCORE: TAKIM ID BULMA ────────────────────────────────────────────────
_team_id_cache = {}

def get_sofascore_team_id(team_name):
    """Takım adından Sofascore team ID bul"""
    if team_name in _team_id_cache:
        return _team_id_cache[team_name]
    try:
        r = requests.get(
            f"{SOFA_URL}/search/all",
            params={"q": team_name},
            headers=SOFA_HEADERS, timeout=10
        )
        if r.status_code != 200:
            return None
        results = r.json().get("results", [])
        # Önce tam eşleşme ara
        name_lower = team_name.lower()
        for item in results:
            if item.get("type") == "team":
                entity = item.get("entity", {})
                if entity.get("sport", {}).get("slug") == "football":
                    ename = entity.get("name", "").lower()
                    if ename == name_lower or name_lower in ename or ename in name_lower:
                        tid = entity.get("id")
                        _team_id_cache[team_name] = tid
                        return tid
        # İlk football takımını döndür
        for item in results:
            if item.get("type") == "team":
                entity = item.get("entity", {})
                if entity.get("sport", {}).get("slug") == "football":
                    tid = entity.get("id")
                    _team_id_cache[team_name] = tid
                    return tid
        return None
    except Exception as e:
        print(f"Sofascore team search error: {e}")
        return None

# ─── SOFASCORE: TAKIM SON MAÇLARı ─────────────────────────────────────────────
def get_sofascore_events(team_id, page=0):
    """Sofascore'dan takımın son maçlarını çek"""
    try:
        r = requests.get(
            f"{SOFA_URL}/team/{team_id}/events/last/{page}",
            headers=SOFA_HEADERS, timeout=10
        )
        if r.status_code != 200:
            return []
        return r.json().get("events", [])
    except Exception as e:
        print(f"Sofascore events error: {e}")
        return []

def stats_from_sofascore(events, team_id, fixture_id=None):
    """Sofascore maç verilerinden stats hesapla"""
    home_scored, home_conceded = [], []
    away_scored, away_conceded = [], []
    scored_all, conceded_all, ht_scored_all = [], [], []

    finished = [e for e in events if e.get("status", {}).get("type") == "finished"]
    # Analiz edilecek maçı listeden çıkar (bugünkü maç dahil olmasın)
    if fixture_id:
        finished = [e for e in finished if e.get("id") != fixture_id]
    finished = sorted(finished, key=lambda x: x.get("startTimestamp", 0))[-10:]

    for m in finished:
        home_team = m.get("homeTeam", {})
        is_home = home_team.get("id") == team_id
        hs = m.get("homeScore", {})
        as_ = m.get("awayScore", {})

        ft_h = hs.get("current")
        ft_a = as_.get("current")
        ht_h = hs.get("period1")
        ht_a = as_.get("period1")

        if ft_h is None or ft_a is None:
            continue

        gf = ft_h if is_home else ft_a
        ga = ft_a if is_home else ft_h
        ht_gf = (ht_h if is_home else ht_a) or 0

        scored_all.append(gf)
        conceded_all.append(ga)
        ht_scored_all.append(ht_gf)

        if is_home:
            home_scored.append(gf)
            home_conceded.append(ga)
        else:
            away_scored.append(gf)
            away_conceded.append(ga)

    if len(scored_all) < 4:
        return None

    avg_sh = sum(home_scored) / max(len(home_scored), 1)
    avg_sa = sum(away_scored) / max(len(away_scored), 1)
    avg_ch = sum(home_conceded) / max(len(home_conceded), 1)
    avg_ca = sum(away_conceded) / max(len(away_conceded), 1)
    avg_st = sum(scored_all) / len(scored_all)
    avg_ct = sum(conceded_all) / len(conceded_all)
    btts = sum(1 for s, c in zip(scored_all, conceded_all) if s > 0 and c > 0) / len(scored_all)
    total_ft = sum(scored_all)
    ht_ratio = max(0.15, min(0.55, sum(ht_scored_all) / total_ft if total_ft > 0 else 0.27))

    h_att = cap_att(avg_sh / LIG_ORT if avg_sh > 0 else 1.0)
    h_def = cap_def(avg_ch / LIG_ORT if avg_ch > 0 else 1.0)
    a_att = cap_att(avg_sa / LIG_ORT if avg_sa > 0 else 1.0)
    a_def = cap_def(avg_ca / LIG_ORT if avg_ca > 0 else 1.0)

    # Ham maç listesi
    recent_matches = []
    for m in finished:
        home_team = m.get("homeTeam", {})
        away_team = m.get("awayTeam", {})
        hs = m.get("homeScore", {})
        as_ = m.get("awayScore", {})
        recent_matches.append({
            "date": datetime.utcfromtimestamp(m.get("startTimestamp", 0)).strftime("%Y-%m-%d"),
            "home_team": home_team.get("name"),
            "away_team": away_team.get("name"),
            "score": f"{hs.get('current', '?')} - {as_.get('current', '?')}",
            "ht_score": f"{hs.get('period1', '?')} - {as_.get('period1', '?')}",
            "tournament": m.get("tournament", {}).get("name", ""),
        })

    print(f"Sofascore stats [{team_id}]: h_att={h_att:.3f} h_def={h_def:.3f} a_att={a_att:.3f} a_def={a_def:.3f} maç={len(scored_all)}")

    return {
        "home_attack":  round(h_att, 4),
        "home_defence": round(h_def, 4),
        "away_attack":  round(a_att, 4),
        "away_defence": round(a_def, 4),
        "general": {
            "avg_scored": avg_st, "goals_scored": sum(scored_all),
            "goals_conceded": sum(conceded_all), "btts_rate": btts,
            "ht_goal_ratio": ht_ratio, "tempo_score": avg_st + avg_ct
        },
        "home": {"avg_scored": avg_sh, "goals_scored": sum(home_scored), "goals_conceded": sum(home_conceded)},
        "away": {"avg_scored": avg_sa, "goals_scored": sum(away_scored), "goals_conceded": sum(away_conceded)},
        "recent_matches": recent_matches,
    }

def get_team_stats_sofascore(team_name, sofa_team_id=None, fixture_id=None):
    """Sofascore'dan takım stats çek"""
    try:
        team_id = sofa_team_id or get_sofascore_team_id(team_name)
        if not team_id:
            print(f"Sofascore: {team_name} bulunamadı")
            return None
        time.sleep(0.3)  # Rate limit
        events = get_sofascore_events(team_id, 0)
        if len(events) < 4:
            events2 = get_sofascore_events(team_id, 1)
            events = events2 + events
        if len(events) < 4:
            print(f"Sofascore: {team_name} yetersiz maç ({len(events)})")
            return None
        return stats_from_sofascore(events, team_id, fixture_id=fixture_id)
    except Exception as e:
        print(f"Sofascore team stats error: {e}")
        return None

# ─── ALLSPORTS: FIXTURE YEDEK ────────────────────────────────────────────────
def get_fixtures_allsports(date):
    try:
        r = requests.get(AS_URL, params={
            "met": "Fixtures", "APIkey": AS_KEY, "from": date, "to": date
        }, timeout=30)
        if r.status_code != 200:
            return []
        matches = r.json().get("result", []) or []
        result = []
        for m in matches:
            home_goals = away_goals = home_ht_goals = away_ht_goals = None
            final = m.get("event_final_result", "")
            if final and " - " in final:
                parts = final.split(" - ")
                try:
                    home_goals = int(parts[0].strip())
                    away_goals = int(parts[1].strip())
                except: pass
            ht = m.get("event_halftime_result", "")
            if ht and " - " in ht:
                ht_parts = ht.split(" - ")
                try:
                    home_ht_goals = int(ht_parts[0].strip())
                    away_ht_goals = int(ht_parts[1].strip())
                except: pass
            status_raw = str(m.get("event_status", ""))
            if status_raw == "Finished": status = "FT"
            elif "'" in status_raw: status = "1H"
            else: status = "NS"
            result.append({
                "fixture_id": int(m.get("event_key", 0)),
                "date": date,
                "time": m.get("event_date", date) + "T" + m.get("event_time", "00:00") + ":00+01:00",
                "status": status,
                "home_team_id": int(m.get("home_team_key", 0)),
                "home_team_name": m.get("event_home_team", ""),
                "away_team_id": int(m.get("away_team_key", 0)),
                "away_team_name": m.get("event_away_team", ""),
                "home_goals": home_goals,
                "away_goals": away_goals,
                "home_ht_goals": home_ht_goals,
                "away_ht_goals": away_ht_goals,
                "league_id": int(m.get("league_key", 0)),
                "league_name": m.get("league_name", ""),
                "country": m.get("country_name", ""),
                "season": m.get("league_year", str(datetime.now().year)),
            })
        return result
    except Exception as e:
        print(f"AllSports fixtures error: {e}")
        return []

# ─── ANA STATS FONKSİYONU ────────────────────────────────────────────────────
def get_team_stats(team_id, league_id, season, team_name=None, sofa_team_id=None, fixture_id=None):
    """
    Öncelik: Sofascore → Default
    """
    # Sofascore dene
    if team_name or sofa_team_id:
        stats = get_team_stats_sofascore(team_name, sofa_team_id, fixture_id=fixture_id)
        if stats:
            print(f"✓ Sofascore stats: {team_name}")
            return stats

    print(f"⚠ Default stats: {team_name or team_id}")
    return default_stats()
