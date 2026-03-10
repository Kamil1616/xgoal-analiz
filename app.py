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
    cached = cache.get(f"fixtures_{date_str}", ttl_minutes=30)
    if cached:
        return cached
    raw = get_fixtures(date_str)
    fixtures = []
    for f in raw:
        fix = f.get("fixture", {})
        teams = f.get("teams", {})
        goals = f.get("goals", {})
        league = f.get("league", {})
        fixtures.append({
            "fixture_id": fix.get("id"),
            "date": fix.get("date"),
            "status": fix.get("status", {}).get("short"),
            "elapsed": fix.get("status", {}).get("elapsed"),
            "home_team_id": teams.get("home", {}).get("id"),
            "home_team_name": teams.get("home", {}).get("name"),
            "away_team_id": teams.get("away", {}).get("id"),
            "away_team_name": teams.get("away", {}).get("name"),
            "home_goals": goals.get("home") if fix.get("status", {}).get("short") != "NS" else None,
            "away_goals": goals.get("away") if fix.get("status", {}).get("short") != "NS" else None,

            "league_id": league.get("id"),
            "league_name": league.get("name"),
            "season": league.get("season"),
        })
    # Saate gore sirala
    fixtures.sort(key=lambda x: x.get("date") or "")
    cache.set(f"fixtures_{date_str}", fixtures)
    return fixtures


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/fixtures")
def api_fixtures():
    date = request.args.get("date", datetime.now().strftime("%Y-%m-%d"))
    try:
        fixtures = get_fixtures_for_date(date)
        return jsonify({"fixtures": fixtures, "date": date})
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

        home_stats = get_team_stats(fix["home_team_id"], league_id, season, team_name=fix.get("home_team_name"))
        away_stats = get_team_stats(fix["away_team_id"], league_id, season, team_name=fix.get("away_team_name"))

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
                home_stats = get_team_stats(fix["home_team_id"], league_id, season, team_name=fix.get("home_team_name"))
                away_stats = get_team_stats(fix["away_team_id"], league_id, season, team_name=fix.get("away_team_name"))
                analysis = run_analysis(
                    home_stats_general=home_stats["general"],
                    home_stats_home=home_stats["home"],
                    away_stats_general=away_stats["general"],
                    away_stats_away=away_stats["away"],
                    home_stats=home_stats,
                    away_stats=away_stats,
                )
                cache.set(analysis_key, analysis)
                results.append({"fixture": fix, "analysis": analysis})
            except:
                continue
        return jsonify({"results": results, "date": date})
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
                    home_stats = get_team_stats(fix["home_team_id"], league_id, season, team_name=fix.get("home_team_name"))
                    away_stats = get_team_stats(fix["away_team_id"], league_id, season, team_name=fix.get("away_team_name"))
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

@app.route("/api/test-sofascore")
def test_sofascore():
    from api.football_api import get_team_stats_sofascore
    result = get_team_stats_sofascore("Arsenal")
    return jsonify({"result": result, "ok": result is not None})

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
