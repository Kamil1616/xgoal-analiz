import os
import requests
from datetime import datetime, timedelta
import time

# ─── API KEYS ─────────────────────────────────────────────────────────────────
AS_KEY = os.environ.get("ALLSPORTS_KEY", "")
AS_URL = "https://apiv2.allsportsapi.com/football"

LIG_ORT = 1.25  # value_hunting_xgoal.py ile aynı olmalı

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

        # Sadece istenen tarihe ait maçları filtrele (UTC+3) + duplicate temizle
        seen_ids = set()
        filtered = []
        for e in all_events:
            eid = e.get("id")
            if eid in seen_ids:
                continue
            seen_ids.add(eid)
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
                st = "LIVE"
            else:
                st = "NS"

            # Dakika hesapla (canlı maçlar için)
            # Sofascore status_code: 6=1.yarı, 7=2.yarı, 60=devre arası, 31=uzatma
            # time_obj: currentPeriodStartTimestamp + initial (saniye) = periyot başlangıcı
            elapsed_min = None
            if status_type == "inprogress":
                import time as _time
                time_obj = e.get("time", {})
                period_start = time_obj.get("currentPeriodStartTimestamp")
                initial = time_obj.get("initial", 0)  # saniye cinsinden (2700=45dk)

                if status_desc and "halftime" in status_desc.lower():
                    elapsed_min = "HT"
                elif period_start:
                    # Periyot içinde geçen dakika
                    elapsed_secs = _time.time() - period_start
                    period_min = int(elapsed_secs / 60)
                    # initial: 0=1.yarı başı, 2700=2.yarı başı (45dk)
                    initial_min = int(initial / 60)
                    elapsed_min = max(1, min(120, initial_min + period_min))
                else:
                    elapsed_min = None

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
                "elapsed": elapsed_min,
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
        # UCL ve büyük Avrupa turnuvaları için ek çekim
        UCL_SEASON_IDS = {
            7: 63814,    # UEFA Champions League 2025/26
            679: 63816,  # UEFA Europa League 2025/26
        }
        for tid, sid in UCL_SEASON_IDS.items():
            try:
                r = requests.get(
                    f"{SOFA_URL}/unique-tournament/{tid}/season/{sid}/events/last/0",
                    headers=SOFA_HEADERS, timeout=10
                )
                if r.status_code == 200:
                    for e in r.json().get("events", []):
                        eid = e.get("id")
                        if eid in seen_ids:
                            continue
                        ts2 = e.get("startTimestamp", 0)
                        local_dt2 = datetime.utcfromtimestamp(ts2 + 10800)
                        if local_dt2.strftime("%Y-%m-%d") == date:
                            seen_ids.add(eid)
                            filtered.append(e)
                            # Bu maçı da result'a ekle
                            home2 = e.get("homeTeam", {})
                            away2 = e.get("awayTeam", {})
                            t2 = e.get("tournament", {})
                            ut2 = t2.get("uniqueTournament", {})
                            st2 = e.get("status", {})
                            st2_type = st2.get("type", "notstarted")
                            hs2 = e.get("homeScore", {})
                            as2 = e.get("awayScore", {})
                            ft2 = "FT" if st2_type == "finished" else ("1H" if st2_type == "inprogress" else "NS")
                            mt2 = local_dt2.strftime("%Y-%m-%dT%H:%M:%S+03:00")
                            result.append({
                                "fixture_id": eid,
                                "date": date,
                                "time": mt2,
                                "status": ft2,
                                "elapsed": st2.get("description"),
                                "home_team_id": home2.get("id"),
                                "home_team_name": home2.get("name"),
                                "away_team_id": away2.get("id"),
                                "away_team_name": away2.get("name"),
                                "home_goals": hs2.get("current"),
                                "away_goals": as2.get("current"),
                                "home_ht_goals": hs2.get("period1"),
                                "away_ht_goals": as2.get("period1"),
                                "league_id": ut2.get("id"),
                                "league_name": t2.get("name"),
                                "country": ut2.get("category", {}).get("name", ""),
                                "season": str(datetime.now().year),
                            })
            except Exception as ex:
                print(f"UCL fetch error: {ex}")

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
    """
    Sofascore maç verilerinden Dixon-Coles stats hesapla.

    Katsayılar lig ortalamasına (LIG_ORT) göre normalize edilir:
      home_attack  = evdeki gol ortalamam / LIG_ORT
      home_defence = evde yediğim gol ortalamam / LIG_ORT
      away_attack  = deplasmanki gol ortalamam / LIG_ORT
      away_defence = deplasmanki yediğim gol ortalamam / LIG_ORT

    Bu katsayılar value_hunting'de ÇAPRAZ kullanılır:
      λ_home = home_attack(ev) × away_defence(dep) × LIG_ORT × EV_AVANTAJI
      λ_away = away_attack(dep) × home_defence(ev) × LIG_ORT

    Exponential decay: son maça en yüksek ağırlık (0.5^0=1, 0.5^1=0.5, ...)
    """
    CUP_KEYWORDS = [
        "cup", "kupa", "copa", "coupe", "pokal", "supercup", "super cup",
        "fa cup", "league cup", "carabao", "friendly", "hazirlik", "superliga cup"
    ]

    finished = []
    for e in events:
        if e.get("status", {}).get("type") != "finished":
            continue
        t_name = e.get("tournament", {}).get("name", "").lower()
        if any(kw in t_name for kw in CUP_KEYWORDS):
            continue
        finished.append(e)

    if fixture_id:
        finished = [e for e in finished if e.get("id") != fixture_id]

    # Son 8 maç, en yeni en sonda
    finished = sorted(finished, key=lambda x: x.get("startTimestamp", 0))[-8:]

    if len(finished) < 3:
        return None

    n = len(finished)
    # Exponential decay ağırlıkları: en son maça ağırlık=1, önceki=0.75, ...
    DECAY = 0.75
    weights = [DECAY ** (n - 1 - i) for i in range(n)]
    w_total = sum(weights)

    home_sc_w, home_co_w = 0.0, 0.0
    away_sc_w, away_co_w = 0.0, 0.0
    home_w_total, away_w_total = 0.0, 0.0
    sc_w, co_w, ht_w, ft_w = 0.0, 0.0, 0.0, 0.0
    btts_w = 0.0

    recent_matches = []
    for idx, m in enumerate(finished):
        w = weights[idx]
        is_home = m.get("homeTeam", {}).get("id") == team_id
        hs = m.get("homeScore", {})
        as_ = m.get("awayScore", {})

        ft_h = hs.get("current")
        ft_a = as_.get("current")
        ht_h = hs.get("period1") or 0
        ht_a = as_.get("period1") or 0

        if ft_h is None or ft_a is None:
            continue

        gf = ft_h if is_home else ft_a
        ga = ft_a if is_home else ft_h
        ht_gf = ht_h if is_home else ht_a

        sc_w  += gf * w
        co_w  += ga * w
        ht_w  += ht_gf * w
        ft_w  += gf * w  # toplam atılan (ht ratio için)
        btts_w += (1 if gf > 0 and ga > 0 else 0) * w

        if is_home:
            home_sc_w += gf * w
            home_co_w += ga * w
            home_w_total += w
        else:
            away_sc_w += gf * w
            away_co_w += ga * w
            away_w_total += w

        recent_matches.append({
            "date": datetime.utcfromtimestamp(m.get("startTimestamp", 0)).strftime("%Y-%m-%d"),
            "home_team": m.get("homeTeam", {}).get("name"),
            "away_team": m.get("awayTeam", {}).get("name"),
            "score": f"{ft_h} - {ft_a}",
            "ht_score": f"{ht_h} - {ht_a}",
            "tournament": m.get("tournament", {}).get("name", ""),
        })

    if w_total == 0:
        return None

    # Ağırlıklı ortalamalar
    avg_st = sc_w / w_total
    avg_ct = co_w / w_total
    avg_ht_scored = ht_w / w_total
    btts = btts_w / w_total

    avg_sh = (home_sc_w / home_w_total) if home_w_total > 0 else avg_st * 1.1
    avg_sa = (away_sc_w / away_w_total) if away_w_total > 0 else avg_st * 0.9
    avg_ch = (home_co_w / home_w_total) if home_w_total > 0 else avg_ct * 0.9
    avg_ca = (away_co_w / away_w_total) if away_w_total > 0 else avg_ct * 1.1

    # HT gol oranı: IY atılan / FT atılan
    ht_ratio = max(0.18, min(0.45, avg_ht_scored / avg_st if avg_st > 0 else 0.28))

    # ─── Dixon-Coles katsayıları — LIG_ORT'a göre normalize ───
    # home_attack  = evde gol atma gücüm (lig ortalamasına göre)
    # home_defence = evde gol yeme zayıflığım (yüksek = kötü savunma)
    # away_attack  = deplasmanki gol atma gücüm
    # away_defence = deplasmanki gol yeme zayıflığım
    h_att = cap_att(avg_sh / LIG_ORT)
    h_def = cap_def(avg_ch / LIG_ORT)
    a_att = cap_att(avg_sa / LIG_ORT)
    a_def = cap_def(avg_ca / LIG_ORT)

    print(f"Sofascore stats [{team_id}]: h_att={h_att:.3f} h_def={h_def:.3f} "
          f"a_att={a_att:.3f} a_def={a_def:.3f} maç={n} (ağırlıklı)")

    return {
        "home_attack":  round(h_att, 4),
        "home_defence": round(h_def, 4),
        "away_attack":  round(a_att, 4),
        "away_defence": round(a_def, 4),
        "general": {
            "avg_scored": round(avg_st, 3),
            "goals_scored": round(sc_w, 1),
            "goals_conceded": round(co_w, 1),
            "btts_rate": round(btts, 3),
            "ht_goal_ratio": round(ht_ratio, 3),
            "tempo_score": round(avg_st + avg_ct, 3),
        },
        "home": {
            "avg_scored": round(avg_sh, 3),
            "goals_scored": round(home_sc_w, 1),
            "goals_conceded": round(home_co_w, 1),
        },
        "away": {
            "avg_scored": round(avg_sa, 3),
            "goals_scored": round(away_sc_w, 1),
            "goals_conceded": round(away_co_w, 1),
        },
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
        if len(events) < 3:
            events2 = get_sofascore_events(team_id, 1)
            events = events2 + events
        if len(events) < 3:
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
