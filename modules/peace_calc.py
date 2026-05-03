"""
M4 PEACECalculator — 16 indicators (PPT-confirmed, 2026-05-03)

P Profitability (1-4):  5-yr revenue, gross margin rate, operating income, EPS — positive & no decline
E Growth       (5-7):  5-yr revenue, operating income, EPS — positive growth trend
A Cash         (8-10): OpCF+FreeCF positive & growing, OpCF > Investing+Financing CF, Earnings Quality > 0.8
C Conservative (11-13):D/E < 0.5, Current ratio > 1, LT debt / Net income < 4
E Efficiency   (14-16):5yr ROE > 15%, Asset turnover > industry avg, ROIC > WACC

Priority tiebreakers: #4, #7, #8, #10, #11, #14
"""

from typing import Optional
from .confidence import official, inferred, user


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _last_n(data: dict[int, float], n: int = 5) -> list[float]:
    if not data:
        return []
    years = sorted(data.keys(), reverse=True)[:n]
    return [data[y] for y in sorted(years)]


def _all_positive(vals: list[float]) -> bool:
    return bool(vals) and all(v > 0 for v in vals)


def _no_decline(vals: list[float]) -> bool:
    """Overall trend is not declining: last value >= first value."""
    if len(vals) < 2:
        return bool(vals)
    return vals[-1] >= vals[0]


def _positive_no_decline(vals: list[float]) -> bool:
    return _all_positive(vals) and _no_decline(vals)


def _positive_growth(vals: list[float]) -> bool:
    """All positive AND last > first (growing trend)."""
    if len(vals) < 2:
        return False
    return _all_positive(vals) and vals[-1] > vals[0]


def _make_indicator(id: int, category: str, name: str, threshold: str,
                    pass_: bool, actual_value, note: str = "",
                    source: str = "sec_edgar", missing: bool = False) -> dict:
    return {
        "id": id,
        "category": category,
        "name": name,
        "threshold": threshold,
        "pass": pass_,
        "actual_value": actual_value,
        "note": note,
        "source": source,
        "confidence": "high" if source == "sec_edgar" else ("medium" if source == "yahoo_finance" else "unverified"),
        "missing_data": missing,
    }


# ──────────────────────────────────────────────
# Main calculator
# ──────────────────────────────────────────────

def calculate_peace(
    financials: dict,
    industry_asset_turnover_avg: Optional[float] = None,
    roic: Optional[float] = None,
    wacc: Optional[float] = None,
) -> dict:
    rev = _last_n(financials.get("revenue", {}))
    gm_rate = _last_n(financials.get("gross_margin_rate", {}))
    op_inc = _last_n(financials.get("operating_income", {}))
    eps = _last_n(financials.get("eps", {}))
    op_cf = _last_n(financials.get("operating_cf", {}))
    inv_cf = _last_n(financials.get("investing_cf", {}))
    fin_cf = _last_n(financials.get("financing_cf", {}))
    free_cf = _last_n(financials.get("free_cf", {}))
    lt_debt = _last_n(financials.get("long_term_debt", {}), 1)
    equity = _last_n(financials.get("equity", {}), 1)
    total_debt = _last_n(financials.get("total_debt", {}), 1)
    cur_assets = _last_n(financials.get("current_assets", {}), 1)
    cur_liab = _last_n(financials.get("current_liabilities", {}), 1)
    net_income = _last_n(financials.get("net_income", {}))
    total_assets = _last_n(financials.get("total_assets", {}), 1)
    revenue_latest = _last_n(financials.get("revenue", {}), 1)

    indicators = []

    # ── P Profitability ──────────────────────────────────
    # 1: 5年總營收為正、不衰退
    vals1 = rev
    indicators.append(_make_indicator(
        1, "P 盈利", "5年總營收為正、不衰退",
        "5年正且不衰退",
        _positive_no_decline(vals1),
        f"{[round(v/1e9,1) for v in vals1]} B",
        missing=not vals1,
    ))

    # 2: 5年毛利率為正、不衰退
    vals2 = gm_rate
    indicators.append(_make_indicator(
        2, "P 盈利", "5年毛利率為正、不衰退",
        "5年正且不衰退",
        _positive_no_decline(vals2),
        f"{[round(v,1) for v in vals2]} %",
        note="毛利率 = (營收 - COGS) / 營收",
        missing=not vals2,
    ))

    # 3: 5年營業利益為正、不衰退
    vals3 = op_inc
    indicators.append(_make_indicator(
        3, "P 盈利", "5年營業利益為正、不衰退",
        "5年正且不衰退",
        _positive_no_decline(vals3),
        f"{[round(v/1e9,1) for v in vals3]} B",
        missing=not vals3,
    ))

    # 4: 5年EPS為正、不衰退 ★
    vals4 = eps
    indicators.append(_make_indicator(
        4, "P 盈利", "5年EPS為正、不衰退",
        "5年正且不衰退",
        _positive_no_decline(vals4),
        str([round(v, 2) for v in vals4]),
        missing=not vals4,
    ))

    # ── E Growth ──────────────────────────────────────────
    # 5: 5年總營收正成長
    indicators.append(_make_indicator(
        5, "E 增長", "5年總營收正成長",
        "正成長趨勢",
        _positive_growth(rev),
        f"{[round(v/1e9,1) for v in rev]} B",
        missing=not rev,
    ))

    # 6: 5年營業利益正成長
    indicators.append(_make_indicator(
        6, "E 增長", "5年營業利益正成長",
        "正成長趨勢",
        _positive_growth(op_inc),
        f"{[round(v/1e9,1) for v in op_inc]} B",
        missing=not op_inc,
    ))

    # 7: 5年EPS正成長 ★
    indicators.append(_make_indicator(
        7, "E 增長", "5年EPS正成長",
        "正成長趨勢",
        _positive_growth(eps),
        str([round(v, 2) for v in eps]),
        missing=not eps,
    ))

    # ── A Cash ────────────────────────────────────────────
    # 8: 營運CF + 自由CF持續增加且皆為正 ★
    op_cf_ok = _positive_growth(op_cf)
    free_cf_ok = _positive_growth(free_cf)
    pass8 = op_cf_ok and free_cf_ok
    indicators.append(_make_indicator(
        8, "A 現金", "營運CF、自由CF持續增加且皆為正",
        "兩者皆>0且持續增加",
        pass8,
        f"OpCF {[round(v/1e9,1) for v in op_cf]}B | FreeCF {[round(v/1e9,1) for v in free_cf]}B",
        missing=not op_cf,
    ))

    # 9: 營運CF > 融資CF + 投資CF
    if op_cf and inv_cf and fin_cf:
        latest_op = op_cf[-1]
        latest_other = abs(inv_cf[-1]) + abs(fin_cf[-1])
        pass9 = latest_op > latest_other
        note9 = f"OpCF {round(latest_op/1e9,1)}B vs |InvCF|+|FinCF| {round(latest_other/1e9,1)}B"
    else:
        pass9 = False
        note9 = "資料不足"
    indicators.append(_make_indicator(
        9, "A 現金", "營運CF > 融資+投資CF",
        "本業CF > 外部CF（絕對值）",
        pass9, note9,
        missing=not op_cf,
    ))

    # 10: 收益質量 (OpCF / 淨利) > 0.8 ★
    if op_cf and net_income:
        ni_latest = net_income[-1]
        eq_val = op_cf[-1] / ni_latest if ni_latest != 0 else None
        pass10 = eq_val is not None and eq_val > 0.8
    else:
        eq_val = None
        pass10 = False
    indicators.append(_make_indicator(
        10, "A 現金", "收益質量 (OpCF / 淨利) > 0.8",
        "> 0.8",
        pass10,
        round(eq_val, 3) if eq_val else "N/A",
        missing=not op_cf or not net_income,
    ))

    # ── C Conservative ────────────────────────────────────
    # 11: D/E ratio < 0.5 ★
    if equity and equity[0] != 0:
        debt_val = total_debt[0] if total_debt else (lt_debt[0] if lt_debt else None)
        de = debt_val / equity[0] if debt_val is not None else None
        pass11 = de is not None and de < 0.5
    else:
        de = None
        pass11 = False
    indicators.append(_make_indicator(
        11, "C 保守", "D/E ratio < 0.5",
        "< 0.5",
        pass11,
        round(de, 3) if de is not None else "N/A",
        missing=not equity,
    ))

    # 12: 流動比率 > 100%（> 200% 更好）
    if cur_assets and cur_liab and cur_liab[0] != 0:
        cr = cur_assets[0] / cur_liab[0]
        pass12 = cr >= 1.0
        note12 = "優選 ≥ 2.0" if cr < 2.0 else "優質（≥ 2.0）"
    else:
        cr = None
        pass12 = False
        note12 = "資料不足"
    indicators.append(_make_indicator(
        12, "C 保守", "流動比率 > 100%（> 200% 更好）",
        "≥ 1.0 合格，≥ 2.0 優選",
        pass12,
        round(cr, 2) if cr else "N/A",
        note=note12,
        missing=not cur_assets,
    ))

    # 13: 長期負債 / 淨利 < 4
    if lt_debt and net_income and net_income[-1] != 0:
        ltdni = lt_debt[0] / net_income[-1]
        pass13 = ltdni < 4
    else:
        ltdni = None
        pass13 = False
    indicators.append(_make_indicator(
        13, "C 保守", "長期負債 / 淨利 < 4",
        "< 4（巴菲特法則）",
        pass13,
        round(ltdni, 2) if ltdni else "N/A",
        missing=not lt_debt,
    ))

    # ── E Efficiency ──────────────────────────────────────
    # 14: 5年ROE > 15% ★
    roe_vals = []
    eq_years = sorted(financials.get("equity", {}).keys(), reverse=True)[:5]
    ni_years = sorted(financials.get("net_income", {}).keys(), reverse=True)[:5]
    common_years = sorted(set(eq_years) & set(ni_years))
    for y in common_years:
        eq_y = financials["equity"].get(y)
        ni_y = financials["net_income"].get(y)
        if eq_y and ni_y and eq_y != 0:
            roe_vals.append(ni_y / eq_y * 100)
    pass14 = bool(roe_vals) and all(r > 15 for r in roe_vals)
    indicators.append(_make_indicator(
        14, "E 效率", "5年ROE > 15%",
        "5年均 > 15%",
        pass14,
        f"{[round(r,1) for r in roe_vals]} %",
        missing=not roe_vals,
    ))

    # 15: Asset Turnover > 同行平均
    if revenue_latest and total_assets and total_assets[0] != 0 and industry_asset_turnover_avg:
        at = revenue_latest[0] / total_assets[0]
        pass15 = at > industry_asset_turnover_avg
        note15 = f"公司 {round(at,3)} vs 同業均值 {industry_asset_turnover_avg}"
    else:
        at = None
        pass15 = False
        note15 = "需手動輸入同業平均資產週轉率"
    indicators.append(_make_indicator(
        15, "E 效率", "Asset Turnover > 同行平均",
        "> 同行平均",
        pass15,
        round(at, 3) if at else "N/A",
        note=note15,
        source="sec_edgar" if at else "user_input",
        missing=not revenue_latest or not industry_asset_turnover_avg,
    ))

    # 16: ROIC > WACC
    if roic is not None and wacc is not None:
        pass16 = roic > wacc
    else:
        pass16 = False
    indicators.append(_make_indicator(
        16, "E 效率", "ROIC > WACC",
        "ROIC > WACC",
        pass16,
        f"ROIC {roic}% vs WACC {wacc}%" if roic and wacc else "需手動輸入",
        source="user_input",
        missing=roic is None or wacc is None,
    ))

    # ── Summary ───────────────────────────────────────────
    pass_count = sum(1 for i in indicators if i["pass"])
    missing_count = sum(1 for i in indicators if i["missing_data"])
    priority_ids = {4, 7, 8, 10, 11, 14}
    priority_pass = {str(i["id"]): i["pass"] for i in indicators if i["id"] in priority_ids}

    if pass_count >= 14:
        verdict = "exceptional"
    elif pass_count >= 11:
        verdict = "excellent"
    elif pass_count >= 8:
        verdict = "borderline"
    else:
        verdict = "fail"

    market_phase = {
        "好景氣": "重守 P + E（盈利 + 增長）",
        "景氣平穩": "重守 E 效率（週轉）",
        "壞景氣": "重守 A + C（現金流 + 保守安全）",
    }

    return {
        "ticker": financials.get("ticker"),
        "entity_name": financials.get("entity_name"),
        "indicators": indicators,
        "pass_count": pass_count,
        "fail_count": 16 - pass_count,
        "missing_data_count": missing_count,
        "pass_pct": round(pass_count / 16 * 100, 1),
        "verdict": verdict,
        "verdict_note": "≥11 = excellent（優秀）｜≥14 = exceptional（頂級）",
        "priority_indicators": priority_pass,
        "priority_tiebreaker_note": "多家公司同時通過時，以 #4 #7 #8 #10 #11 #14 排名優先",
        "market_phase_reference": market_phase,
    }
