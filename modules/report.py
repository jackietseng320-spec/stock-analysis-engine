"""M9 ReportGenerator — assemble ABCDE report"""

from datetime import datetime, timezone


def _verdict_emoji(pass_: bool) -> str:
    return "✅" if pass_ else "❌"


def _confidence_badge(level: str) -> str:
    return {"high": "🟢", "medium": "🟡", "low": "🟠", "unverified": "🔴"}.get(level, "⚪")


def generate_report(
    ticker: str,
    horizontal: dict | None = None,
    vertical: dict | None = None,
    qualitative: dict | None = None,
    peace: dict | None = None,
    valuation: dict | None = None,
    options: dict | None = None,
    market_price_info: dict | None = None,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    entity_name = (peace or {}).get("entity_name", ticker)

    # ── A: Horizontal ──────────────────────────────────────────────
    a_section = None
    if horizontal:
        a = horizontal
        alloc = a.get("allocation", {})
        a_section = {
            "section": "A — 水平配置",
            "total_investment": a.get("total_investment"),
            "age": a.get("user_age"),
            "aggressive": f"{alloc.get('aggressive_pct')}% → ${alloc.get('aggressive_amount', 0):,.0f}",
            "defensive": f"{alloc.get('defensive_pct')}% → ${alloc.get('defensive_amount', 0):,.0f}",
            "lottery": f"{alloc.get('lottery_pct')}% → ${alloc.get('lottery_amount', 0):,.0f}",
            "suggested_stocks": a.get("suggested_stock_count"),
            "per_stock_budget": a.get("per_stock_budget"),
            "note": a.get("safety_bucket_note"),
        }

    # ── B: Vertical ─────────────────────────────────────────────────
    b_section = None
    if vertical:
        v = vertical
        b_section = {
            "section": "B — 垂直配置",
            "fair_value": v.get("fair_value"),
            "current_price": v.get("current_price"),
            "current_safety_margin_pct": v.get("current_safety_margin_pct"),
            "current_verdict": v.get("current_verdict"),
            "batches": v.get("batches", []),
            "buyable_count": v.get("buyable_batches_count"),
            "deployed": v.get("deployed_amount"),
            "remaining_cash": v.get("remaining_cash"),
            "options_note": v.get("options_note"),
        }

    # ── C: Qualitative ──────────────────────────────────────────────
    c_section = None
    if qualitative:
        q = qualitative
        moat = q.get("moat_analysis", {})
        risk = q.get("risk_analysis", {})

        moat_lines = []
        for k, v in moat.get("results", {}).items():
            moat_lines.append(f"{_verdict_emoji(v['hit'])} {v['name']}")

        risk_lines = []
        for k, v in risk.get("results", {}).items():
            risk_lines.append(f"{_verdict_emoji(v['pass'])} {v['code']} {v['name']}")

        c_section = {
            "section": "C — 質化分析",
            "moat_summary": f"護城河 {moat.get('hit_count', 0)}/5（{'通過' if moat.get('pass') else '未通過'}）",
            "moat_verdict": moat.get("verdict"),
            "moat_lines": moat_lines,
            "risk_summary": "RISK 全通過" if risk.get("pass") else f"RISK {risk.get('flag_count', 0)} 項風險",
            "risk_lines": risk_lines,
            "review_required": "⚠ 以上為 GPT 推估，必須人工確認",
        }

    # ── D: PEACE + Valuation ───────────────────────────────────────
    d_section = None
    if peace:
        p = peace
        indicators_summary = []
        for ind in p.get("indicators", []):
            indicators_summary.append({
                "id": ind["id"],
                "name": ind["name"],
                "pass": ind["pass"],
                "value": ind["actual_value"],
                "threshold": ind["threshold"],
                "emoji": _verdict_emoji(ind["pass"]),
                "missing": ind.get("missing_data", False),
            })

        d_section = {
            "section": "D — 量化分析（PEACE）",
            "entity": entity_name,
            "pass_count": p.get("pass_count"),
            "fail_count": p.get("fail_count"),
            "missing_data": p.get("missing_data_count"),
            "verdict": p.get("verdict"),
            "verdict_note": p.get("verdict_note"),
            "indicators": indicators_summary,
            "priority_pass": p.get("priority_indicators"),
        }

    # ── D: Valuation ────────────────────────────────────────────────
    d_val_section = None
    if valuation:
        v = valuation
        mp = v.get("current_price", {})
        fv = v.get("primary_fair_value", {})
        d_val_section = {
            "section": "D — 估值",
            "market_price": f"${mp.get('value')} 🟡 {mp.get('delay_note', '')}",
            "fair_value": f"${fv.get('value')} [{fv.get('method')}] {_confidence_badge(fv.get('confidence','low'))}",
            "safety_margin_pct": v.get("safety_margin_pct"),
            "verdict": v.get("verdict"),
            "verdict_label": v.get("verdict_label"),
            "formula": v.get("safety_margin_formula"),
            "all_estimates": v.get("all_estimates", []),
            "update_reminder": v.get("update_reminder"),
        }

    # ── E: Options ──────────────────────────────────────────────────
    e_section = None
    if options:
        o = options
        checks = o.get("checks", {})
        e_section = {
            "section": "E — 選擇權試算",
            "strategy": o.get("strategy"),
            "ticker": o.get("ticker"),
            "strike": o.get("strike_price"),
            "premium": o.get("premium_per_share"),
            "expiry": o.get("expiry"),
            "days_to_expiry": o.get("days_to_expiry"),
            "premium_total": o.get("premium_total"),
            "breakeven": o.get("breakeven"),
            "actual_cost": o.get("actual_cost"),
            "margin_required": o.get("margin_required"),
            "annualized_return_pct": o.get("annualized_return_pct"),
            "prerequisite_pass": checks.get("prerequisite_abcd", {}).get("pass"),
            "budget_ok": checks.get("budget_within_allocation", {}).get("pass"),
            "vertical_note": checks.get("vertical_alignment", {}).get("note"),
            "data_note": o.get("data_note"),
            "warning": o.get("warning"),
        }

    # ── Data source summary ─────────────────────────────────────────
    source_summary = [
        {"item": "財報（EPS / CF / Balance Sheet）", "source": "SEC EDGAR", "type": "confirmed", "confidence": "🟢 high"},
        {"item": "市價", "source": "Yahoo Finance", "type": "public_market", "delay": "15–20 分鐘延遲", "confidence": "🟡 medium"},
        {"item": "公允價值 / 目標價", "source": "使用者輸入", "type": "user_input", "confidence": "🔴 unverified"},
        {"item": "護城河 / RISK", "source": "GPT 推估", "type": "inference", "confidence": "🟠 low，需人工確認"},
        {"item": "選擇權報價", "source": "使用者輸入", "type": "user_input", "confidence": "🔴 unverified"},
    ]

    return {
        "report_meta": {
            "ticker": ticker.upper(),
            "entity_name": entity_name,
            "generated_at": now,
            "version": "1.0",
        },
        "sections": {
            "A_horizontal": a_section,
            "B_vertical": b_section,
            "C_qualitative": c_section,
            "D_peace": d_section,
            "D_valuation": d_val_section,
            "E_options": e_section,
        },
        "data_source_summary": source_summary,
        "global_disclaimer": (
            "本報告基於課程「個人財務逆向工程」ABCDE 方法論。"
            "質化分析為 GPT 推估，估值為系統推算，不構成投資建議。"
            "所有結論需人工確認後方可作為投資依據。"
        ),
    }
