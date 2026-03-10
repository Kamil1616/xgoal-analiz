import os
import requests
from datetime import datetime, timedelta

AS_KEY = os.environ.get("ALLSPORTS_KEY", "")
AS_URL = "https://apiv2.allsportsapi.com/football"

FD_KEY = os.environ.get("FOOTBALL_API_KEY", "") or os.environ.get("FOOTBALL_DATA_KEY", "")
FD_URL = "https://api.football-data.org/v4"
FD_HEADERS = {"X-Auth-Token": FD_KEY}

SOFA_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Android 11; Mobile; rv:109.0) Gecko/109.0 Firefox/109.0",
    "Accept": "application/json",
    "Referer": "https://www.sofascore.com/"
}

BSD_KEY = os.environ.get("BSD_KEY", "1fa9e71c0de4cbe8dabc210a89028e926532740d")
BSD_URL = "https://sports.bzzoiro.com/api"
BSD_HEADERS = {"Authorization": f"Token {BSD_KEY}"}

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

def get_sofascore_team_id(team_name):
    """Takım adından Sofascore ID bul"""
    try:
        r = requests.get(
            f"https://api.sofascore.com/api/v1/search/all",
            params={"q": team_name},
            headers=SOFA_HEADERS,
            timeout=10
        )
        if r.status_code != 200:
            return None
        results = r.json().get("results", [])
        for item in results:
            if item.get("type") == "team":
                entity = item.get("entity", {})
                sport = entity.get("sport", {})
                gender = entity.get("gender", "M")
                if sport.get("slug") == "football" and gender == "M":
                    name = entity.get("name", "").lower()
                    search = team_name.lower()
                    if name == search or search in name or name in search:
                        return entity.get("id")
        # İlk football takımını dön
        for item in results:
            if item.get("type") == "team":
                entity = item.get("entity", {})
                if entity.get("sport", {}).get("slug") == "football":
                    return entity.get("id")
        return None
    except Exception as e:
        print(f"Sofascore search error: {e}")
        return None

def get_sofascore_events(team_id, page=0):
    """Sofascore'dan takımın son maçlarını çek"""
    try:
        r = requests.get(
            f"https://api.sofascore.com/api/v1/team/{team_id}/events/last/{page}",
            headers=SOFA_HEADERS,
            timeout=10
        )
        if r.status_code != 200:
            return []
        return r.json().get("events", [])
    except Exception as e:
        print(f"Sofascore events error: {e}")
        return []

def stats_from_sofascore(events, team_id):
    """Sofascore maç verilerinden stats hesapla"""
    home_scored, home_conceded = [], []
    away_scored, away_conceded = [], []
    scored_all, conceded_all, ht_scored_all = [], [], []

    finished = [e for e in events if e.get("status", {}).get("type") == "finished"]
    finished = finished[-10:]

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

    if not scored_all:
        return None

    lig_ort = 1.35
    avg_sh = sum(home_scored) / max(len(home_scored), 1)
    avg_sa = sum(away_scored) / max(len(away_scored), 1)
    avg_ch = sum(home_conceded) / max(len(home_conceded), 1)
    avg_ca = sum(away_conceded) / max(len(away_conceded), 1)
    avg_st = sum(scored_all) / len(scored_all)
    avg_ct = sum(conceded_all) / len(conceded_all)
    btts = sum(1 for s, c in zip(scored_all, conceded_all) if s > 0 and c > 0) / len(scored_all)
    total_ft = sum(scored_all)
    ht_ratio = max(0.15, min(0.55, sum(ht_scored_all) / total_ft if total_ft > 0 else 0.27))

    return {
        "home_attack":  round(avg_sh / lig_ort if avg_sh > 0 else 1.0, 4),
        "home_defence": round(avg_ch / lig_ort if avg_ch > 0 else 1.0, 4),
        "away_attack":  round(avg_sa / lig_ort if avg_sa > 0 else 1.0, 4),
        "away_defence": round(avg_ca / lig_ort if avg_ca > 0 else 1.0, 4),
        "general": {
            "avg_scored": avg_st, "goals_scored": sum(scored_all),
            "goals_conceded": sum(conceded_all), "btts_rate": btts,
            "ht_goal_ratio": ht_ratio, "tempo_score": avg_st + avg_ct
        },
        "home": {"avg_scored": avg_sh, "goals_scored": sum(home_scored), "goals_conceded": sum(home_conceded)},
        "away": {"avg_scored": avg_sa, "goals_scored": sum(away_scored), "goals_conceded": sum(away_conceded)}
    }

def get_team_stats_sofascore(team_name):
    """Sofascore'dan takım stats çek"""
    try:
        team_id = get_sofascore_team_id(team_name)
        if not team_id:
            return None
        events = get_sofascore_events(team_id, 0)
        if len(events) < 3:
            # Daha fazla maç için sayfa 1'e bak
            events2 = get_sofascore_events(team_id, 1)
            events = events2 + events
        if not events:
            return None
        return stats_from_sofascore(events, team_id)
    except Exception as e:
        print(f"Sofascore team stats error: {e}")
        return None

# ─── ALLSPORTS ────────────────────────────────────────────────────────────────

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
            home_goals = None
            away_goals = None
            home_ht_goals = None
            away_ht_goals = None
            final = m.get("event_final_result", "")
            if final and " - " in final:
                parts = final.split(" - ")
                try:
                    home_goals = int(parts[0].strip())
                    away_goals = int(parts[1].strip())
                except:
                    pass
            ht = m.get("event_halftime_result", "")
            if ht and " - " in ht:
                ht_parts = ht.split(" - ")
                try:
                    home_ht_goals = int(ht_parts[0].strip())
                    away_ht_goals = int(ht_parts[1].strip())
                except:
                    pass
            status_raw = str(m.get("event_status", ""))
            if status_raw == "Finished":
                status = "FT"
            elif "'" in status_raw:
                status = "1H"
            else:
                status = "NS"
            elapsed = None
            if "'" in status_raw:
                try:
                    elapsed = int(status_raw.replace("'", ""))
                except:
                    pass
            result.append({
                "fixture": {
                    "id": int(m.get("event_key", 0)),
                    "date": m.get("event_date", date) + "T" + m.get("event_time", "00:00") + ":00+01:00",
                    "status": {"short": status, "elapsed": elapsed}
                },
                "teams": {
                    "home": {"id": int(m.get("home_team_key", 0)), "name": m.get("event_home_team", "")},
                    "away": {"id": int(m.get("away_team_key", 0)), "name": m.get("event_away_team", "")}
                },
                "goals": {"home": home_goals, "away": away_goals},
                "ht_goals": {"home": home_ht_goals, "away": away_ht_goals},
                "league": {
                    "id": int(m.get("league_key", 0)),
                    "name": m.get("league_name", ""),
                    "season": m.get("league_year", ""),
                    "country": m.get("country_name", "")
                }
            })
        return result
    except Exception as e:
        print(f"AllSports fixtures error: {e}")
        return []

def get_bsd_odds_map(date):
    """BSD den o günün maç oranlarını çek, api_id bazlı map döndür"""
    try:
        r = requests.get(f"{BSD_URL}/events/", headers=BSD_HEADERS, params={
            "date_from": date, "date_to": date
        }, timeout=20)
        if r.status_code != 200:
            return {}
        data = r.json()
        events = data if isinstance(data, list) else data.get("results", [])
        odds_map = {}
        for e in events:
            home = str(e.get("home_team") or "").lower().strip()
            away = str(e.get("away_team") or "").lower().strip()
            key = f"{home}|{away}"
            odds_map[key] = {
                "odds_home": e.get("odds_home"),
                "odds_draw": e.get("odds_draw"),
                "odds_away": e.get("odds_away"),
                "odds_over_15": e.get("odds_over_15"),
                "odds_over_25": e.get("odds_over_25"),
                "odds_over_35": e.get("odds_over_35"),
            }
        return odds_map
    except Exception as e:
        print(f"BSD odds error: {e}")
        return {}

def get_fixtures(date):
    fixtures = get_fixtures_allsports(date)
    if not fixtures:
        fixtures = get_fixtures_fd(date)
    if not fixtures:
        return []

    # BSD oranlarını eşleştir
    try:
        odds_map = get_bsd_odds_map(date)
        if odds_map:
            for fix in fixtures:
                home = (fix.get("home_team_name") or "").lower().strip()
                away = (fix.get("away_team_name") or "").lower().strip()
                # Tam eşleşme dene
                key = f"{home}|{away}"
                odds = odds_map.get(key)
                # Yoksa kısmi eşleşme dene
                if not odds:
                    for k, v in odds_map.items():
                        parts = k.split("|")
                        if len(parts) == 2:
                            bh, ba = parts
                            if (home in bh or bh in home) and (away in ba or ba in away):
                                odds = v
                                break
                if odds:
                    fix.update(odds)
    except Exception as e:
        print(f"BSD odds match error: {e}")

    return fixtures

def get_fixtures_fd(date):
    try:
        date_plus = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        r = requests.get(f"{FD_URL}/matches", headers=FD_HEADERS,
            params={"dateFrom": date, "dateTo": date_plus}, timeout=30)
        if r.status_code != 200:
            return []
        matches = r.json().get("matches", [])
        result = []
        for m in matches:
            comp = m.get("competition", {})
            home = m.get("homeTeam", {})
            away = m.get("awayTeam", {})
            ft = m.get("score", {}).get("fullTime", {})
            status = m.get("status", "TIMED")
            st_map = {"IN_PLAY": "1H", "HALFTIME": "HT", "FINISHED": "FT", "TIMED": "NS", "SCHEDULED": "NS"}
            result.append({
                "fixture": {"id": m.get("id"), "date": m.get("utcDate"),
                    "status": {"short": st_map.get(status, "NS"), "elapsed": None}},
                "teams": {"home": {"id": home.get("id"), "name": home.get("name")},
                    "away": {"id": away.get("id"), "name": away.get("name")}},
                "goals": {"home": ft.get("home"), "away": ft.get("away")},
                "league": {"id": comp.get("id"), "name": comp.get("name"), "season": None}
            })
        return result
    except Exception as e:
        print(f"FD fixtures error: {e}")
        return []

def get_bsd_raw(date_from, date_to):
    """BSD events raw data - debug için"""
    try:
        r = requests.get(f"{BSD_URL}/events/", headers=BSD_HEADERS, params={
            "date_from": date_from, "date_to": date_to
        }, timeout=20)
        if r.status_code != 200:
            return None, r.status_code
        return r.json(), 200
    except Exception as e:
        return None, str(e)

def get_bsd_events_for_team(team_name):
    """BSD API den takım adıyla son maçları çek"""
    name_lower = team_name.lower()
    team_matches = []
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=270)).strftime("%Y-%m-%d")
        page = 1
        while len(team_matches) < 10 and page <= 6:
            r = requests.get(f"{BSD_URL}/events/", headers=BSD_HEADERS, params={
                "date_from": from_date, "date_to": today, "page": page
            }, timeout=20)
            if r.status_code != 200:
                break
            data = r.json()
            events = data if isinstance(data, list) else data.get("results", [])
            if not events:
                break
            for e in events:
                home_name = str(e.get("home_team") or "").lower()
                away_name = str(e.get("away_team") or "").lower()
                if name_lower in home_name or home_name in name_lower or                    name_lower in away_name or away_name in name_lower:
                    team_matches.append(e)
            page += 1
    except Exception as e:
        print(f"BSD fetch error: {e}")
    return team_matches

def get_team_stats_bsd(team_name):
    """BSD xG bazlı takım stats"""
    if not team_name:
        return None
    try:
        matches = get_bsd_events_for_team(team_name)
        if len(matches) < 4:
            return None
        return stats_from_bsd(matches, team_name)
    except Exception as e:
        print(f"BSD team stats error: {e}")
        return None

def stats_from_bsd(matches, team_name):
    """BSD xG verilerinden stats hesapla"""
    home_xg_att, home_xg_def = [], []
    away_xg_att, away_xg_def = [], []
    xg_att_all, xg_def_all = [], []
    scored_all = []
    name_lower = team_name.lower()

    finished = [m for m in matches if str(m.get("status","")).lower() == "finished"]
    finished = sorted(finished, key=lambda x: x.get("event_date",""))[-10:]

    for m in finished:
        home_name = str(m.get("home_team") or "").lower()
        is_home = name_lower in home_name or home_name in name_lower
        hxg = m.get("actual_home_xg")
        axg = m.get("actual_away_xg")
        if hxg is None or axg is None:
            continue
        try:
            hxg, axg = float(hxg), float(axg)
        except:
            continue
        hg = m.get("home_score") or 0
        ag = m.get("away_score") or 0
        try:
            hg, ag = int(hg), int(ag)
        except:
            hg, ag = 0, 0
        xg_for = hxg if is_home else axg
        xg_against = axg if is_home else hxg
        gf = hg if is_home else ag
        xg_att_all.append(xg_for)
        xg_def_all.append(xg_against)
        scored_all.append(gf)
        if is_home:
            home_xg_att.append(xg_for)
            home_xg_def.append(xg_against)
        else:
            away_xg_att.append(xg_for)
            away_xg_def.append(xg_against)

    if len(xg_att_all) < 4:
        return None

    lig_ort = 1.35
    avg_hxg_att = sum(home_xg_att) / max(len(home_xg_att), 1)
    avg_axg_att = sum(away_xg_att) / max(len(away_xg_att), 1)
    avg_hxg_def = sum(home_xg_def) / max(len(home_xg_def), 1)
    avg_axg_def = sum(away_xg_def) / max(len(away_xg_def), 1)
    avg_xg_att = sum(xg_att_all) / len(xg_att_all)
    avg_xg_def = sum(xg_def_all) / len(xg_def_all)
    btts = sum(1 for a, d in zip(xg_att_all, xg_def_all) if a > 0.5 and d > 0.5) / len(xg_att_all)

    return {
        "home_attack":  round(avg_hxg_att / lig_ort if avg_hxg_att > 0 else 1.0, 4),
        "home_defence": round(avg_hxg_def / lig_ort if avg_hxg_def > 0 else 1.0, 4),
        "away_attack":  round(avg_axg_att / lig_ort if avg_axg_att > 0 else 1.0, 4),
        "away_defence": round(avg_axg_def / lig_ort if avg_axg_def > 0 else 1.0, 4),
        "general": {
            "avg_scored": avg_xg_att, "goals_scored": round(sum(xg_att_all), 2),
            "goals_conceded": round(sum(xg_def_all), 2), "btts_rate": btts,
            "ht_goal_ratio": 0.27, "tempo_score": avg_xg_att + avg_xg_def
        },
        "home": {"avg_scored": avg_hxg_att, "goals_scored": round(sum(home_xg_att), 2), "goals_conceded": round(sum(home_xg_def), 2)},
        "away": {"avg_scored": avg_axg_att, "goals_scored": round(sum(away_xg_att), 2), "goals_conceded": round(sum(away_xg_def), 2)}
    }
def merge_stats_weighted(recent_stats, all_stats, recent_w=0.65, old_w=0.35):
    """Son 5 maç %65, eski maçlar %35 ağırlıklı birleştir"""
    if recent_stats is None:
        return all_stats
    if all_stats is None:
        return recent_stats
    def blend(a, b, wa, wb):
        return round(a * wa + b * wb, 4)
    return {
        "home_attack":  blend(recent_stats["home_attack"],  all_stats["home_attack"],  recent_w, old_w),
        "home_defence": blend(recent_stats["home_defence"], all_stats["home_defence"], recent_w, old_w),
        "away_attack":  blend(recent_stats["away_attack"],  all_stats["away_attack"],  recent_w, old_w),
        "away_defence": blend(recent_stats["away_defence"], all_stats["away_defence"], recent_w, old_w),
        "general": {
            "avg_scored":    blend(recent_stats["general"]["avg_scored"],    all_stats["general"]["avg_scored"],    recent_w, old_w),
            "goals_scored":  recent_stats["general"]["goals_scored"],
            "goals_conceded":recent_stats["general"]["goals_conceded"],
            "btts_rate":     blend(recent_stats["general"]["btts_rate"],     all_stats["general"]["btts_rate"],     recent_w, old_w),
            "ht_goal_ratio": blend(recent_stats["general"]["ht_goal_ratio"], all_stats["general"]["ht_goal_ratio"], recent_w, old_w),
            "tempo_score":   blend(recent_stats["general"]["tempo_score"],   all_stats["general"]["tempo_score"],   recent_w, old_w),
        },
        "home": recent_stats["home"],
        "away": recent_stats["away"],
    }

def get_team_stats(team_id, league_id, season, team_name=None):
    """BSD xG önce, sonra AllSports. Son 5 maç ağırlıklı form."""
    recent_stats = None
    all_stats = None

    # BSD xG ile stats
    if team_name:
        all_stats = get_team_stats_bsd(team_name)
        if all_stats:
            print(f"BSD xG stats: {team_name}")
            # Son 5 maç için ayrıca çek
            recent_matches = get_bsd_events_for_team(team_name)
            finished = [m for m in recent_matches if str(m.get("status","")).lower() == "finished"]
            finished = sorted(finished, key=lambda x: x.get("event_date",""))[-5:]
            if len(finished) >= 3:
                recent_stats = stats_from_bsd(finished, team_name)
            return merge_stats_weighted(recent_stats, all_stats)

    # BSD başarısız → AllSports
    all_stats = get_team_stats_allsports(team_id)
    if all_stats and all_stats["general"]["goals_scored"] > 0:
        print(f"AllSports stats: {team_id}")
        # Son 5 maç ağırlığı AllSports'tan
        recent_stats = get_team_stats_allsports_recent(team_id, limit=5)
        return merge_stats_weighted(recent_stats, all_stats)

    return default_stats()

def get_team_stats_allsports_recent(team_id, limit=5):
    """AllSports son N maç stats"""
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=120)).strftime("%Y-%m-%d")
        r = requests.get(AS_URL, params={
            "met": "Fixtures", "APIkey": AS_KEY,
            "teamId": team_id, "from": from_date, "to": today
        }, timeout=30)
        if r.status_code != 200:
            return None
        matches = r.json().get("result", []) or []
        tid = int(team_id)
        finished = [
            m for m in matches
            if m.get("event_status") == "Finished"
            and m.get("event_final_result")
            and (int(m.get("home_team_key", 0)) == tid or int(m.get("away_team_key", 0)) == tid)
        ]
        finished = finished[-limit:]
        if len(finished) < 3:
            return None
        return stats_from_allsports(finished, team_id)
    except:
        return None

def get_team_stats_allsports(team_id):
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        r = requests.get(AS_URL, params={
            "met": "Fixtures", "APIkey": AS_KEY,
            "teamId": team_id, "from": from_date, "to": today
        }, timeout=30)
        if r.status_code != 200:
            return None
        matches = r.json().get("result", []) or []
        tid = int(team_id)
        # Sadece bu takımın gerçekten oynadığı maçları al
        finished = [
            m for m in matches
            if m.get("event_status") == "Finished"
            and m.get("event_final_result")
            and (int(m.get("home_team_key", 0)) == tid or int(m.get("away_team_key", 0)) == tid)
        ]
        finished = finished[-10:]
        if not finished:
            return None
        return stats_from_allsports(finished, team_id)
    except Exception as e:
        print(f"AllSports team stats error: {e}")
        return None

def stats_from_allsports(matches, team_id):
    home_scored, home_conceded = [], []
    away_scored, away_conceded = [], []
    scored_all, conceded_all, ht_scored_all = [], [], []
    tid = int(team_id)
    for m in matches:
        try:
            home_id = int(m.get("home_team_key", 0))
            away_id = int(m.get("away_team_key", 0))
        except:
            home_id = 0; away_id = 0
        if home_id != tid and away_id != tid:
            continue
        is_home = (home_id == tid)
        final = m.get("event_final_result", "")
        if not final or " - " not in final:
            continue
        parts = final.split(" - ")
        try:
            hg, ag = int(parts[0].strip()), int(parts[1].strip())
        except:
            continue
        gf = hg if is_home else ag
        ga = ag if is_home else hg
        ht = m.get("event_halftime_result", "")
        ht_gf = 0
        if ht and " - " in ht:
            ht_parts = ht.split(" - ")
            try:
                ht_gf = int(ht_parts[0].strip()) if is_home else int(ht_parts[1].strip())
            except:
                pass
        scored_all.append(gf)
        conceded_all.append(ga)
        ht_scored_all.append(ht_gf)
        if is_home:
            home_scored.append(gf)
            home_conceded.append(ga)
        else:
            away_scored.append(gf)
            away_conceded.append(ga)
    if len(scored_all) < 6:
        return None
    lig_ort = 1.35
    avg_sh = sum(home_scored) / max(len(home_scored), 1)
    avg_sa = sum(away_scored) / max(len(away_scored), 1)
    avg_ch = sum(home_conceded) / max(len(home_conceded), 1)
    avg_ca = sum(away_conceded) / max(len(away_conceded), 1)
    avg_st = sum(scored_all) / len(scored_all)
    avg_ct = sum(conceded_all) / len(conceded_all)
    btts = sum(1 for s, c in zip(scored_all, conceded_all) if s > 0 and c > 0) / len(scored_all)
    total_ft = sum(scored_all)
    ht_ratio = max(0.15, min(0.55, sum(ht_scored_all) / total_ft if total_ft > 0 else 0.27))
    return {
        "home_attack":  round(avg_sh / lig_ort if avg_sh > 0 else 1.0, 4),
        "home_defence": round(avg_ch / lig_ort if avg_ch > 0 else 1.0, 4),
        "away_attack":  round(avg_sa / lig_ort if avg_sa > 0 else 1.0, 4),
        "away_defence": round(avg_ca / lig_ort if avg_ca > 0 else 1.0, 4),
        "general": {
            "avg_scored": avg_st, "goals_scored": sum(scored_all),
            "goals_conceded": sum(conceded_all), "btts_rate": btts,
            "ht_goal_ratio": ht_ratio, "tempo_score": avg_st + avg_ct
        },
        "home": {"avg_scored": avg_sh, "goals_scored": sum(home_scored), "goals_conceded": sum(home_conceded)},
        "away": {"avg_scored": avg_sa, "goals_scored": sum(away_scored), "goals_conceded": sum(away_conceded)}
    }
