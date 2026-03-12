import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, render_template, jsonify, request
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev")

from api.football_api import get_fixtures, get_team_stats
from api import cache
from models.value_hunting import run_analysis


def get_fixtures_for_date(date_str):
    """Bugün: her zaman taze çek. Geçmiş/gelecek: 30 dk cache."""
    today = datetime.now().strftime("%Y-%m-%d")

    if date_str != today:
        # Geçmiş veya gelecek gün — cache kullan
        cached = cache.get(f"fixtures_{date_str}", ttl_minutes=30)
        if cached:
            return cached
        fixtures = get_fixtures(date_str)
        fixtures.sort(key=lambda x: x.get("time") or "")
        cache.set(f"fixtures_{date_str}", fixtures)
        return fixtures

    # Bugün — canlı maç olabilir, 1 dk cache
    cached = cache.get(f"fixtures_{date_str}", ttl_minutes=1)
    if cached:
        return cached
    fixtures = get_fixtures(date_str)
    fixtures.sort(key=lambda x: x.get("time") or "")
    cache.set(f"fixtures_{date_str}", fixtures)
    return fixtures


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/fixtures")
def api_fixtures():
    date = request.args.get("date", datetime.now().strftime("%Y-%m-%d"))
    download = request.args.get("download", "0")
    try:
        fixtures = get_fixtures_for_date(date)
        data = {"fixtures": fixtures, "date": date, "count": len(fixtures)}
        if download == "1":
            from flask import Response
            import json
            return Response(
                json.dumps(data, ensure_ascii=False, indent=2),
                mimetype="application/json",
                headers={"Content-Disposition": f"attachment; filename=fixtures_{date}.json"}
            )
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e), "fixtures": []}), 500


@app.route("/api/analyze/<int:fixture_id>")
def api_analyze(fixture_id):
    date = request.args.get("date", datetime.now().strftime("%Y-%m-%d"))
    try:
        fixtures = get_fixtures_for_date(date)
        fix = next((f for f in fixtures if f["fixture_id"] == fixture_id), None)
        if not fix:
            return jsonify({"error": "Mac bulunamadi"}), 404

        analysis_key = f"analysis_{fixture_id}"
        cached = cache.get(analysis_key, ttl_minutes=60)
        if cached:
            return jsonify({"fixture": fix, "analysis": cached})

        season = fix.get("season") or 2025
        league_id = fix.get("league_id") or 39

        fid = fix.get("fixture_id")
        home_stats = get_team_stats(fix["home_team_id"], league_id, season, team_name=fix.get("home_team_name"), sofa_team_id=fix.get("home_team_id"), fixture_id=fid)
        away_stats = get_team_stats(fix["away_team_id"], league_id, season, team_name=fix.get("away_team_name"), sofa_team_id=fix.get("away_team_id"), fixture_id=fid)

        # Default stats kullanılıyorsa uyar
        home_is_default = home_stats["general"]["goals_scored"] == 27
        away_is_default = away_stats["general"]["goals_scored"] == 27

        # BSD oranlarını fixture'dan al
        odds_home = fix.get("odds_home")
        odds_draw = fix.get("odds_draw")
        odds_away = fix.get("odds_away")

        analysis = run_analysis(
            home_stats_general=home_stats["general"],
            home_stats_home=home_stats["home"],
            away_stats_general=away_stats["general"],
            away_stats_away=away_stats["away"],
            home_stats=home_stats,
            away_stats=away_stats,
            odds_home=odds_home,
            odds_draw=odds_draw,
            odds_away=odds_away,
        )
        analysis["data_warning"] = home_is_default or away_is_default
        cache.set(analysis_key, analysis)
        return jsonify({"fixture": fix, "analysis": analysis})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/analyze-all")
def api_analyze_all():
    date = request.args.get("date", datetime.now().strftime("%Y-%m-%d"))
    download = request.args.get("download", "0")
    try:
        fixtures = get_fixtures_for_date(date)
        results = []
        for fix in fixtures[:50]:
            try:
                analysis_key = f"analysis_{fix['fixture_id']}"
                cached = cache.get(analysis_key, ttl_minutes=60)
                if cached:
                    results.append({"fixture": fix, "analysis": cached})
                    continue
                season = fix.get("season") or 2025
                league_id = fix.get("league_id") or 39
                fid = fix.get("fixture_id")
                home_stats = get_team_stats(fix["home_team_id"], league_id, season, team_name=fix.get("home_team_name"), sofa_team_id=fix.get("home_team_id"), fixture_id=fid)
                away_stats = get_team_stats(fix["away_team_id"], league_id, season, team_name=fix.get("away_team_name"), sofa_team_id=fix.get("away_team_id"), fixture_id=fid)
                analysis = run_analysis(
                    home_stats_general=home_stats["general"],
                    home_stats_home=home_stats["home"],
                    away_stats_general=away_stats["general"],
                    away_stats_away=away_stats["away"],
                    home_stats=home_stats,
                    away_stats=away_stats,
                )
                analysis["data_warning"] = home_stats["general"]["goals_scored"] == 27
                analysis["home_stats"] = {
                    "team": fix.get("home_team_name"),
                    "home_attack": home_stats["home_attack"],
                    "home_defence": home_stats["home_defence"],
                    "away_attack": home_stats["away_attack"],
                    "away_defence": home_stats["away_defence"],
                    "avg_scored": home_stats["general"]["avg_scored"],
                    "btts_rate": home_stats["general"]["btts_rate"],
                    "ht_goal_ratio": home_stats["general"]["ht_goal_ratio"],
                    "recent_matches": home_stats.get("recent_matches", []),
                }
                analysis["away_stats"] = {
                    "team": fix.get("away_team_name"),
                    "home_attack": away_stats["home_attack"],
                    "home_defence": away_stats["home_defence"],
                    "away_attack": away_stats["away_attack"],
                    "away_defence": away_stats["away_defence"],
                    "avg_scored": away_stats["general"]["avg_scored"],
                    "btts_rate": away_stats["general"]["btts_rate"],
                    "ht_goal_ratio": away_stats["general"]["ht_goal_ratio"],
                    "recent_matches": away_stats.get("recent_matches", []),
                }
                cache.set(analysis_key, analysis)
                results.append({"fixture": fix, "analysis": analysis})
            except:
                continue

        data = {"date": date, "count": len(results), "results": results}

        if download == "1":
            from flask import Response
            import json
            return Response(
                json.dumps(data, ensure_ascii=False, indent=2),
                mimetype="application/json",
                headers={"Content-Disposition": f"attachment; filename=analiz_{date}.json"}
            )
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route("/api/signals")
def api_signals():
    date = request.args.get("date", datetime.now().strftime("%Y-%m-%d"))
    try:
        fixtures = get_fixtures_for_date(date)
        signals = []
        import time
        deadline = time.time() + 25
        for fix in fixtures:
            if time.time() > deadline:
                break
            try:
                analysis_key = f"analysis_{fix['fixture_id']}"
                cached = cache.get(analysis_key, ttl_minutes=60)
                if cached:
                    analysis = cached
                else:
                    season = fix.get("season") or 2025
                    league_id = fix.get("league_id") or 39
                    fid = fix.get("fixture_id")
                    home_stats = get_team_stats(fix["home_team_id"], league_id, season, team_name=fix.get("home_team_name"), sofa_team_id=fix.get("home_team_id"), fixture_id=fid)
                    away_stats = get_team_stats(fix["away_team_id"], league_id, season, team_name=fix.get("away_team_name"), sofa_team_id=fix.get("away_team_id"), fixture_id=fid)
                    analysis = run_analysis(
                        home_stats_general=home_stats["general"],
                        home_stats_home=home_stats["home"],
                        away_stats_general=away_stats["general"],
                        away_stats_away=away_stats["away"],
                        home_stats=home_stats,
                        away_stats=away_stats,
                    )
                    cache.set(analysis_key, analysis)

                iy_sigs = analysis.get("iy_signals", [])
                ms_sigs = analysis.get("ms_signals", [])
                min_prob = float(request.args.get("min_prob", 0))
                if min_prob > 0:
                    iy_sigs = [s for s in iy_sigs if s.get("probability", 0) >= min_prob]
                    ms_sigs = [s for s in ms_sigs if s.get("probability", 0) >= min_prob]
                if iy_sigs or ms_sigs:
                    signals.append({
                        "fixture": fix,
                        "iy_signals": iy_sigs,
                        "ms_signals": ms_sigs,
                        "iyms_top": (analysis.get("iyms_results") or [{}])[0],
                        "lambda_home": analysis.get("lambda_home"),
                        "lambda_away": analysis.get("lambda_away"),
                    })
            except:
                continue
        from flask import Response
        import json
        download = request.args.get("download", "0")
        result = {
            "date": date,
            "total_analyzed": len(fixtures),
            "signal_count": len(signals),
            "signals": signals
        }
        if download == "1":
            return Response(
                json.dumps(result, ensure_ascii=False, indent=2),
                mimetype='application/json',
                headers={"Content-Disposition": f"attachment;filename=signals-{date}.json"}
            )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/clear-cache", methods=["POST","GET"])
def clear_cache():
    import shutil
    cache_dir = "instance/cache"
    if os.path.exists(cache_dir):
        shutil.rmtree(cache_dir)
        os.makedirs(cache_dir, exist_ok=True)
    return jsonify({"status": "ok", "message": "Cache temizlendi"})


@app.route("/api/debug-stats")
def api_debug_stats():
    """Takım stats debug - ?home=TakımAdı&away=TakımAdı"""
    home_name = request.args.get("home", "")
    away_name = request.args.get("away", "")
    home_id = int(request.args.get("home_id", 0))
    away_id = int(request.args.get("away_id", 0))
    if not home_name or not away_name:
        return jsonify({"error": "home ve away parametresi gerekli"}), 400
    home_stats = get_team_stats(home_id, 0, 2025, team_name=home_name)
    away_stats = get_team_stats(away_id, 0, 2025, team_name=away_name)
    from models.value_hunting import compute_lambdas, compute_lambda_iy
    lh, la = compute_lambdas(home_stats, away_stats)
    liy = compute_lambda_iy(lh, la, home_stats, away_stats)
    return jsonify({
        "home": {"name": home_name, "stats": home_stats},
        "away": {"name": away_name, "stats": away_stats},
        "lambda_home": lh, "lambda_away": la,
        "lambda_total": round(lh+la, 3), "lambda_iy": liy
    })

@app.route("/api/test-sportoto")
def api_test_sportoto():
    """Spor Toto API test"""
    import requests
    urls = [
        "https://webapi.sportoto.gov.tr/api/sporttoto/list",
        "https://webapi.sportoto.gov.tr/sporttoto/list",
        "https://webapi.sportoto.gov.tr/api/list",
        "https://webapi.sportoto.gov.tr/api/sporttoto/currentweek",
        "https://webapi.sportoto.gov.tr/api/sporttoto/week",
    ]
    results = {}
    for url in urls:
        try:
            r = requests.get(url, timeout=8, headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
                "Referer": "https://www.sportoto.gov.tr/"
            })
            results[url.split("/")[-1]] = {
                "status": r.status_code,
                "preview": r.text[:200] if r.status_code == 200 else r.text[:100]
            }
        except Exception as e:
            results[url.split("/")[-1]] = {"error": str(e)}
    return jsonify(results)

@app.route("/api/debug-live")
def api_debug_live():
    """Canlı maçların ham Sofascore verisini göster"""
    import requests
    today = datetime.now().strftime("%Y-%m-%d")
    headers = {
        "User-Agent": "Mozilla/5.0 (Android 11; Mobile; rv:109.0) Gecko/109.0 Firefox/109.0",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.sofascore.com/",
        "Origin": "https://www.sofascore.com",
    }
    try:
        r = requests.get(
            f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{today}",
            headers=headers, timeout=10
        )
        events = r.json().get("events", [])
        live = []
        for e in events:
            if e.get("status", {}).get("type") == "inprogress":
                live.append({
                    "id": e.get("id"),
                    "home": e.get("homeTeam", {}).get("name"),
                    "away": e.get("awayTeam", {}).get("name"),
                    "status_code": e.get("status", {}).get("code"),
                    "status_desc": e.get("status", {}).get("description"),
                    "time_obj": e.get("time", {}),
                })
        return jsonify({"live_count": len(live), "matches": live})
    except Exception as ex:
        return jsonify({"error": str(ex)})

@app.route("/api/test-sofascore")
def api_test_sofascore():
    """Sofascore bağlantı testi - bugünün maçları"""
    import requests
    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    headers = {
        "User-Agent": "Mozilla/5.0 (Android 11; Mobile; rv:109.0) Gecko/109.0 Firefox/109.0",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "tr-TR,tr;q=0.9",
        "Referer": "https://www.sofascore.com/",
        "Origin": "https://www.sofascore.com",
        "Cache-Control": "no-cache",
    }
    results = {}
    # Test 1: Günlük maçlar
    try:
        r = requests.get(
            f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{today}",
            headers=headers, timeout=10
        )
        results["scheduled"] = {"status": r.status_code, "count": len(r.json().get("events", [])) if r.status_code == 200 else 0}
    except Exception as e:
        results["scheduled"] = {"error": str(e)}

    # Test 2: Takım arama
    try:
        r2 = requests.get(
            "https://api.sofascore.com/api/v1/search/all",
            params={"q": "Galatasaray"},
            headers=headers, timeout=10
        )
        results["search"] = {"status": r2.status_code, "found": len(r2.json().get("results", [])) if r2.status_code == 200 else 0}
    except Exception as e:
        results["search"] = {"error": str(e)}

    # Test 3: Takım son maçları (Galatasaray ID: 2564)
    try:
        r3 = requests.get(
            "https://api.sofascore.com/api/v1/team/2564/events/last/0",
            headers=headers, timeout=10
        )
        results["team_events"] = {"status": r3.status_code, "count": len(r3.json().get("events", [])) if r3.status_code == 200 else 0}
    except Exception as e:
        results["team_events"] = {"error": str(e)}

    return jsonify(results)

@app.route("/api/test-fotmob")
def api_test_fotmob():
    """FotMob bağlantı testi"""
    import requests
    try:
        r = requests.get(
            "https://www.fotmob.com/api/matches",
            params={"date": "20260310"},
            headers={
                "User-Agent": "Mozilla/5.0 (Android 11; Mobile; rv:109.0) Gecko/109.0 Firefox/109.0",
                "Accept": "application/json",
                "Referer": "https://www.fotmob.com/"
            },
            timeout=10
        )
        data = r.json()
        leagues = data.get("leagues", [])
        return jsonify({
            "status": r.status_code,
            "league_count": len(leagues),
            "leagues": [l.get("name") for l in leagues[:10]]
        })
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/api/test-bsd")
def api_test_bsd():
    """BSD takım adlarını listele - hangi takımlar var?"""
    from api.football_api import get_bsd_raw
    from datetime import datetime, timedelta
    today = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    data, status = get_bsd_raw(from_date, today)
    if data is None:
        return jsonify({"error": str(status)}), 500
    events = data if isinstance(data, list) else data.get("results", [])
    # Tüm takım adlarını topla
    teams = set()
    for e in events:
        if e.get("home_team"): teams.add(e["home_team"])
        if e.get("away_team"): teams.add(e["away_team"])
    # Türk takımlarını filtrele (basit heuristik)
    tr_keywords = ["spor", "sport", "sk", "fk", "fc", "beşiktaş", "galatasaray",
                   "fenerbahçe", "trabzon", "başak", "adana", "vanspor", "van",
                   "istanbul", "ankara", "izmir", "bursaspor", "konyaspor"]
    tr_teams = [t for t in teams if any(k in t.lower() for k in tr_keywords)]
    return jsonify({
        "total_events": len(events),
        "total_teams": len(teams),
        "tr_teams": sorted(tr_teams),
        "all_teams_sample": sorted(list(teams))[:50]
    })

@app.route("/api/debug")
def api_debug():
    import requests as req
    date = datetime.now().strftime("%Y-%m-%d")
    key = os.environ.get("FOOTBALL_API_KEY","") or os.environ.get("FOOTBALL_DATA_KEY","")
    try:
        r = req.get(
            "https://api.football-data.org/v4/matches",
            headers={"X-Auth-Token": key},
            params={"dateFrom": date, "dateTo": date},
            timeout=15
        )
        data = r.json()
        matches = data.get("matches", [])
        return jsonify({
            "status": r.status_code,
            "results": len(matches),
            "errors": data.get("message","") if r.status_code != 200 else {},
            "date": date,
            "key_set": bool(key),
            "remaining": r.headers.get("X-Requests-Available-Minute","?")
        })
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/api/dates")
def api_dates():
    today = datetime.now()
    dates = [(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(-1, 4)]
    return jsonify({"dates": dates})


if __name__ == "__main__":
    os.makedirs("instance/cache", exist_ok=True)
    app.run(debug=True, port=5000)
