import os
import requests
from datetime import datetime, timedelta

# ─── API KEYS ─────────────────────────────────────────────────────────────────
AS_KEY = os.environ.get("ALLSPORTS_KEY", "")
AS_URL = "https://apiv2.allsportsapi.com/football"

LIG_ORT = 1.35

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

def cap_att(v): return max(0.3, min(2.0, v))
def cap_def(v): return max(0.5, min(1.8, v))

# ─── FIXTURES ─────────────────────────────────────────────────────────────────
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
            elapsed = None
            if "'" in status_raw:
                try: elapsed = int(status_raw.replace("'", ""))
                except: pass
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

def get_fixtures(date):
    return get_fixtures_allsports(date)

# ─── STATS ────────────────────────────────────────────────────────────────────
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
            continue
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
            except: pass
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

    print(f"AllSports [{team_id}]: h_att={h_att:.3f} h_def={h_def:.3f} a_att={a_att:.3f} a_def={a_def:.3f} maç={len(scored_all)}")

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
        "away": {"avg_scored": avg_sa, "goals_scored": sum(away_scored), "goals_conceded": sum(away_conceded)}
    }

def get_team_stats_allsports(team_id):
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        r = requests.get(AS_URL, params={
            "met": "Fixtures", "APIkey": AS_KEY,
            "teamId": team_id, "from": from_date, "to": today
        }, timeout=30)
        if r.status_code != 200:
            print(f"AllSports HTTP {r.status_code} for teamId={team_id}")
            return None
        matches = r.json().get("result", []) or []
        tid = int(team_id)
        finished = [
            m for m in matches
            if m.get("event_status") == "Finished"
            and m.get("event_final_result")
            and (int(m.get("home_team_key", 0)) == tid or int(m.get("away_team_key", 0)) == tid)
        ]
        finished = finished[-10:]
        if len(finished) < 4:
            print(f"AllSports: teamId={team_id} için yetersiz maç ({len(finished)})")
            return None
        stats = stats_from_allsports(finished, team_id)
        if stats is None:
            return None
        # Ham maç listesini stats'a ekle
        stats["recent_matches"] = [
            {
                "date": m.get("event_date"),
                "home_team": m.get("event_home_team"),
                "away_team": m.get("event_away_team"),
                "score": m.get("event_final_result"),
                "ht_score": m.get("event_halftime_result"),
                "league": m.get("league_name"),
            }
            for m in finished
        ]
        return stats
    except Exception as e:
        print(f"AllSports team stats error: {e}")
        return None

# ─── ANA STATS FONKSİYONU ─────────────────────────────────────────────────────
def get_team_stats(team_id, league_id, season, team_name=None):
    """AllSports → Default"""
    if team_id and int(team_id) > 0:
        stats = get_team_stats_allsports(team_id)
        if stats:
            print(f"✓ AllSports stats: {team_name or team_id}")
            return stats
    print(f"⚠ Default stats: {team_name or team_id}")
    return default_stats()
