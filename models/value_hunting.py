import math

DC_RHO = -0.14
LIG_ORT = 1.35
EV_AVANTAJI = 1.15

# ─── SINYAL EŞİKLERİ ──────────────────────────────────────────────────────────
SIGNAL_THRESHOLDS = {"0.5": 0.82, "1.5": 0.75, "2.5": 0.60, "3.5": 0.50}
MS_SIGNAL_THRESHOLDS = {"1": 0.55, "X": 0.35, "2": 0.50}
FT_OVER_THRESHOLDS = {"1.5": 0.85, "2.5": 0.75, "3.5": 0.65}

# ─── TEMEL FONKSIYONLAR ───────────────────────────────────────────────────────
def poisson_prob(lam, k):
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return (math.exp(-lam) * (lam ** k)) / math.factorial(k)

def dixon_coles_correction(home_goals, away_goals, lambda_home, lambda_away, rho=DC_RHO):
    if home_goals == 0 and away_goals == 0:
        return 1 - lambda_home * lambda_away * rho
    elif home_goals == 0 and away_goals == 1:
        return 1 + lambda_home * rho
    elif home_goals == 1 and away_goals == 0:
        return 1 + lambda_away * rho
    elif home_goals == 1 and away_goals == 1:
        return 1 - rho
    return 1.0

def score_matrix(lambda_home, lambda_away, max_goals=8):
    matrix = {}
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            p = poisson_prob(lambda_home, h) * poisson_prob(lambda_away, a)
            p *= dixon_coles_correction(h, a, lambda_home, lambda_away)
            matrix[(h, a)] = p
    total = sum(matrix.values())
    if total > 0:
        matrix = {k: v / total for k, v in matrix.items()}
    return matrix

# ─── LAMBDA HESAPLAMA ─────────────────────────────────────────────────────────
def compute_lambdas(home_stats, away_stats):
    h_att = home_stats.get("home_attack", 1.0)
    h_def = home_stats.get("home_defence", 1.0)
    a_att = away_stats.get("away_attack", 1.0)
    a_def = away_stats.get("away_defence", 1.0)

    lambda_home = h_att * a_def * LIG_ORT * EV_AVANTAJI
    lambda_away = a_att * h_def * LIG_ORT

    lambda_home = max(0.3, min(4.0, lambda_home))
    lambda_away = max(0.3, min(4.0, lambda_away))

    return round(lambda_home, 3), round(lambda_away, 3)

def compute_lambda_iy(lambda_home, lambda_away, home_stats, away_stats):
    lambda_total = lambda_home + lambda_away
    ht_home = home_stats.get("general", {}).get("ht_goal_ratio", 0.27)
    ht_away = away_stats.get("general", {}).get("ht_goal_ratio", 0.27)
    ht_ratio = (ht_home + ht_away) / 2
    ht_ratio = max(0.15, min(0.55, ht_ratio))
    lambda_iy = lambda_total * ht_ratio
    btts = (home_stats.get("general", {}).get("btts_rate", 0.45) +
            away_stats.get("general", {}).get("btts_rate", 0.45)) / 2
    if btts > 0.6:
        lambda_iy *= 1.05
    return round(lambda_iy, 3)

# ─── OLASILIK HESAPLAMALARI ───────────────────────────────────────────────────
def compute_halftime_probs(lambda_home, lambda_away, lambda_iy):
    total = lambda_home + lambda_away
    lh_iy = lambda_iy * (lambda_home / total) if total > 0 else lambda_iy / 2
    la_iy = lambda_iy * (lambda_away / total) if total > 0 else lambda_iy / 2
    ht_probs = {"1": 0, "X": 0, "2": 0}
    for h in range(7):
        for a in range(7):
            p = poisson_prob(lh_iy, h) * poisson_prob(la_iy, a)
            p *= dixon_coles_correction(h, a, lh_iy, la_iy)
            if h > a:    ht_probs["1"] += p
            elif h == a: ht_probs["X"] += p
            else:        ht_probs["2"] += p
    total_ht = sum(ht_probs.values())
    if total_ht > 0:
        ht_probs = {k: v / total_ht for k, v in ht_probs.items()}
    return ht_probs

def compute_iyms_probs(lambda_home, lambda_away, lambda_iy):
    ft_matrix = score_matrix(lambda_home, lambda_away)
    ht_probs = compute_halftime_probs(lambda_home, lambda_away, lambda_iy)
    ft_probs = {"1": 0, "X": 0, "2": 0}
    for (h, a), p in ft_matrix.items():
        if h > a:    ft_probs["1"] += p
        elif h == a: ft_probs["X"] += p
        else:        ft_probs["2"] += p
    iyms = {}
    for ht in ["1", "X", "2"]:
        for ft in ["1", "X", "2"]:
            raw = ht_probs[ht] * ft_probs[ft]
            if ht == ft:
                raw *= 1.35
            elif (ht == "1" and ft == "2") or (ht == "2" and ft == "1"):
                raw *= 0.55
            else:
                raw *= 0.90
            iyms[f"{ht}/{ft}"] = raw
    total = sum(iyms.values())
    if total > 0:
        iyms = {k: v / total for k, v in iyms.items()}
    return iyms

def compute_ms_probs(lambda_home, lambda_away):
    ft_matrix = score_matrix(lambda_home, lambda_away)
    probs = {"1": 0, "X": 0, "2": 0}
    for (h, a), p in ft_matrix.items():
        if h > a:    probs["1"] += p
        elif h == a: probs["X"] += p
        else:        probs["2"] += p
    return probs

def compute_iy_over_probs(lambda_iy):
    def p_at_least(lam, k):
        return 1 - sum(poisson_prob(lam, i) for i in range(k))
    return {
        "0.5": p_at_least(lambda_iy, 1),
        "1.5": p_at_least(lambda_iy, 2),
        "2.5": p_at_least(lambda_iy, 3),
        "3.5": p_at_least(lambda_iy, 4),
    }

def compute_ft_over_probs(lambda_total):
    """Tam maç alt/üst olasılıkları"""
    def p_at_least(lam, k):
        return 1 - sum(poisson_prob(lam, i) for i in range(k))
    return {
        "1.5": p_at_least(lambda_total, 2),
        "2.5": p_at_least(lambda_total, 3),
        "3.5": p_at_least(lambda_total, 4),
    }

# ─── VALUE BET ────────────────────────────────────────────────────────────────
def compute_value_bet(ms_probs, odds_home, odds_draw, odds_away):
    """BSD oranlarından value bet hesapla"""
    results = {}
    market_map = {"1": odds_home, "X": odds_draw, "2": odds_away}
    for outcome, odd in market_map.items():
        if not odd or odd <= 0:
            continue
        market_prob = 1 / odd
        model_prob = ms_probs.get(outcome, 0)
        value = model_prob - market_prob
        if value > 0.05:  # %5+ değer varsa
            results[outcome] = {
                "model_prob": round(model_prob * 100, 1),
                "market_prob": round(market_prob * 100, 1),
                "value": round(value * 100, 1),
                "odd": odd
            }
    return results

# ─── SİNYALLER ────────────────────────────────────────────────────────────────
def get_iy_signals(iy_over_probs):
    signals = []
    for market, prob in iy_over_probs.items():
        if prob >= SIGNAL_THRESHOLDS.get(market, 1.0):
            signals.append({
                "market": f"IY {market} Ust",
                "probability": round(prob * 100, 1),
                "signal": "Guclu Sinyal"
            })
    return signals

def get_ft_over_signals(ft_over_probs):
    """FT alt/üst sinyalleri"""
    signals = []
    for market, prob in ft_over_probs.items():
        if prob >= FT_OVER_THRESHOLDS.get(market, 1.0):
            signals.append({
                "market": f"MS {market} Ust",
                "probability": round(prob * 100, 1),
                "signal": "Guclu Sinyal"
            })
    return signals

def get_ms_signals(ms_probs):
    signals = []
    labels = {"1": "Ev Kazanir", "X": "Beraberlik", "2": "Dep Kazanir"}
    for outcome, prob in ms_probs.items():
        if prob >= MS_SIGNAL_THRESHOLDS.get(outcome, 1.0):
            signals.append({
                "outcome": outcome,
                "label": labels[outcome],
                "probability": round(prob * 100, 1),
                "model_odd": round((1 / prob) * 0.90, 2) if prob > 0 else 999,
                "signal": "Guclu Sinyal"
            })
    return signals

def get_combo_signal(iy_over_probs, lambda_total, lambda_home, lambda_away):
    """Kombine sinyal: IY 0.5>%90 + IY 1.5>%80 + λ Total>4"""
    signals = []
    iy05 = iy_over_probs.get("0.5", 0)
    iy15 = iy_over_probs.get("1.5", 0)
    lam_diff = lambda_home - lambda_away

    if iy05 >= 0.90 and iy15 >= 0.80 and lambda_total >= 4:
        signals.append({
            "type": "COMBO",
            "label": "🔥 GÜÇLÜ GOL SİNYALİ",
            "desc": f"IY 0.5 %{round(iy05*100,1)} + IY 1.5 %{round(iy15*100,1)} + λ={round(lambda_total,2)}",
            "confidence": 92
        })

    if lam_diff >= 1.5:
        signals.append({
            "type": "HOME_FAV",
            "label": "⚡ EV FAVORİ",
            "desc": f"λ fark: {round(lam_diff,2)} (Ev çok güçlü)",
            "confidence": round(79 + (lam_diff - 1.5) * 3, 1)
        })
    elif lam_diff <= -1.5:
        signals.append({
            "type": "AWAY_FAV",
            "label": "⚡ DEPLASMAN FAVORİ",
            "desc": f"λ fark: {round(abs(lam_diff),2)} (Deplasman çok güçlü)",
            "confidence": round(79 + (abs(lam_diff) - 1.5) * 3, 1)
        })

    return signals

# ─── IY+MS SKOR KOMBİNASYONLARI ──────────────────────────────────────────────
def compute_iyms_score_combos(lambda_home, lambda_away, lambda_iy):
    """En olası 3 IY+MS skor kombinasyonu"""
    total = lambda_home + lambda_away
    lh_iy = lambda_iy * (lambda_home / total) if total > 0 else lambda_iy / 2
    la_iy = lambda_iy * (lambda_away / total) if total > 0 else lambda_iy / 2

    combos = {}
    for ht_h in range(5):
        for ht_a in range(5):
            p_ht = poisson_prob(lh_iy, ht_h) * poisson_prob(la_iy, ht_a)
            p_ht *= dixon_coles_correction(ht_h, ht_a, lh_iy, la_iy)
            for add_h in range(6):
                for add_a in range(6):
                    ft_h = ht_h + add_h
                    ft_a = ht_a + add_a
                    p_add = poisson_prob(lambda_home * 0.55, add_h) * poisson_prob(lambda_away * 0.55, add_a)
                    p = p_ht * p_add
                    if p > 0.001:
                        key = f"IY {ht_h}-{ht_a} / MS {ft_h}-{ft_a}"
                        combos[key] = combos.get(key, 0) + p

    total_p = sum(combos.values())
    if total_p > 0:
        combos = {k: v / total_p for k, v in combos.items()}

    top3 = sorted(combos.items(), key=lambda x: x[1], reverse=True)[:3]
    return [{"combo": k, "probability": round(v * 100, 2)} for k, v in top3]

# ─── ANA ANALİZ FONKSİYONU ───────────────────────────────────────────────────
def run_analysis(home_stats_general, home_stats_home, away_stats_general, away_stats_away,
                 home_stats=None, away_stats=None,
                 odds_home=None, odds_draw=None, odds_away=None):

    if home_stats is None:
        home_stats = {
            "home_attack": home_stats_home["avg_scored"] / 1.35,
            "home_defence": home_stats_home.get("goals_conceded", 10) / max(home_stats_home.get("goals_scored", 10), 1),
            "away_attack": away_stats_general["avg_scored"] / 1.35,
            "away_defence": away_stats_general.get("goals_conceded", 20) / max(away_stats_general.get("goals_scored", 20), 1),
            "general": home_stats_general
        }
    if away_stats is None:
        away_stats = {
            "home_attack": home_stats_general["avg_scored"] / 1.35,
            "home_defence": home_stats_general.get("goals_conceded", 20) / max(home_stats_general.get("goals_scored", 20), 1),
            "away_attack": away_stats_away["avg_scored"] / 1.35,
            "away_defence": away_stats_away.get("goals_conceded", 12) / max(away_stats_away.get("goals_scored", 12), 1),
            "general": away_stats_general
        }

    lambda_home, lambda_away = compute_lambdas(home_stats, away_stats)
    lambda_total = lambda_home + lambda_away
    lambda_iy = compute_lambda_iy(lambda_home, lambda_away, home_stats, away_stats)

    iyms_probs = compute_iyms_probs(lambda_home, lambda_away, lambda_iy)
    sorted_iyms = sorted(iyms_probs.items(), key=lambda x: x[1], reverse=True)
    iyms_results = []
    for i, (selection, prob) in enumerate(sorted_iyms):
        fair_odd = 1 / prob if prob > 0 else 999
        iyms_results.append({
            "rank": i + 1,
            "selection": selection,
            "probability": round(prob * 100, 2),
            "model_odd": round(fair_odd * 0.90, 2),
            "site_odd": None,
            "status": None,
            "divider": i == 4
        })

    iy_over_probs = compute_iy_over_probs(lambda_iy)
    ft_over_probs = compute_ft_over_probs(lambda_total)
    ms_probs = compute_ms_probs(lambda_home, lambda_away)

    ms_results = [
        {"outcome": o, "probability": round(ms_probs[o] * 100, 1),
         "model_odd": round((1 / ms_probs[o]) * 0.90, 2) if ms_probs[o] > 0 else 999}
        for o in ["1", "X", "2"]
    ]

    ft_matrix = score_matrix(lambda_home, lambda_away)
    top_scores = sorted(ft_matrix.items(), key=lambda x: x[1], reverse=True)[:3]
    score_probs = {f"{h}-{a}": round(p * 100, 1) for (h, a), p in top_scores}

    iyms_combos = compute_iyms_score_combos(lambda_home, lambda_away, lambda_iy)

    combo_signals = get_combo_signal(iy_over_probs, lambda_total, lambda_home, lambda_away)

    value_bets = {}
    if odds_home or odds_draw or odds_away:
        value_bets = compute_value_bet(ms_probs, odds_home, odds_draw, odds_away)

    ft_over_signals = get_ft_over_signals(ft_over_probs)

    return {
        "lambda_home": round(lambda_home, 3),
        "lambda_away": round(lambda_away, 3),
        "lambda_total": round(lambda_total, 3),
        "lambda_iy": round(lambda_iy, 3),
        "iyms_results": iyms_results,
        "iy_over_probs": {k: round(v * 100, 1) for k, v in iy_over_probs.items()},
        "ft_over_probs": {k: round(v * 100, 1) for k, v in ft_over_probs.items()},
        "iy_signals": get_iy_signals(iy_over_probs),
        "ft_over_signals": ft_over_signals,
        "ms_results": ms_results,
        "ms_signals": get_ms_signals(ms_probs),
        "combo_signals": combo_signals,
        "value_bets": value_bets,
        "score_probs": score_probs,
        "iyms_combos": iyms_combos,
    }
