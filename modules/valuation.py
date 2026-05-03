"""M5 ValuationCalculator"""


def calculate_valuation(
    current_price: float,
    fair_value_manual: float | None = None,
    fair_value_source: str = "user_input",
    eps_ttm: float | None = None,
    pe_hist_avg: float | None = None,
) -> dict:
    estimates = []

    # Method 1: user manual input (highest priority)
    if fair_value_manual:
        estimates.append({
            "method": "手動輸入公允價值",
            "value": fair_value_manual,
            "source": fair_value_source,
            "confidence": "unverified",
            "priority": 1,
        })

    # Method 2: historical PE estimation (only if user manually provided pe_hist_avg)
    if eps_ttm and pe_hist_avg:
        pe_estimate = eps_ttm * pe_hist_avg
        estimates.append({
            "method": f"歷史 PE 法（EPS {round(eps_ttm,2)} × 均值 PE {pe_hist_avg}）",
            "value": round(pe_estimate, 2),
            "source": "system_estimate",
            "confidence": "low",
            "priority": 2,
            "warning": "⚠️ 此為 PE 估算，對高成長科技股（如 MSFT、NVDA）嚴重低估，請以 Morningstar 手動輸入公允價值為準",
        })

    if not estimates:
        return {
            "status": "no_valuation",
            "action_required": "🔴 必須由使用者手動提供公允價值才能估值",
            "note": "請至 Morningstar / 分析師報告 查詢公允價值後，以 fair_value_manual 欄位輸入。禁止由 AI 自行猜測。",
        }

    # Use highest priority estimate as primary
    primary = min(estimates, key=lambda x: x["priority"])
    fair_value = primary["value"]

    safety_margin = round((fair_value - current_price) / fair_value * 100, 2) if fair_value else None

    if safety_margin is None:
        verdict = "unknown"
    elif safety_margin > 0:
        verdict = "undervalued"     # 低估（安全邊際為正 = 市價低於估值）
    elif safety_margin == 0:
        verdict = "fairly_valued"
    else:
        verdict = "overvalued"      # 高估（安全邊際為負 = 市價高於估值）

    return {
        "current_price": {
            "value": current_price,
            "source": "yahoo_finance",
            "delay_note": "可能 15–20 分鐘延遲",
            "confidence": "medium",
        },
        "primary_fair_value": {
            "value": fair_value,
            "method": primary["method"],
            "source": primary["source"],
            "confidence": primary["confidence"],
        },
        "all_estimates": estimates,
        "safety_margin_pct": safety_margin,
        "safety_margin_formula": "(估值 - 市價) / 估值 × 100%",
        "verdict": verdict,
        "verdict_label": {
            "undervalued": "低估（建議關注買入時機）",
            "fairly_valued": "合理估值",
            "overvalued": "高估（耐心等待）",
        }.get(verdict, "未知"),
        "update_reminder": "建議每年更新一次估值與安全邊際",
    }
