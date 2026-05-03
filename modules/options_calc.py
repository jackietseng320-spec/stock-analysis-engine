"""M6 OptionsCalculator — Sell Put / Sell Call (手動輸入報價版)"""

from datetime import date


def _annualized_return(premium_total: float, margin: float, days: int) -> float:
    if margin <= 0 or days <= 0:
        return 0.0
    return round((premium_total / margin) * (365 / days) * 100, 2)


def _days_to_expiry(expiry: str) -> int:
    try:
        exp = date.fromisoformat(expiry)
        today = date.today()
        return max((exp - today).days, 1)
    except Exception:
        return 365


def sell_put(
    ticker: str,
    strike_price: float,
    premium_per_share: float,
    expiry: str,
    contracts: int = 1,
    # Prerequisite checks (from ABCD)
    abcd_pass: bool = False,
    per_batch_budget: float | None = None,
    fair_value: float | None = None,
    vertical_batches: list[dict] | None = None,
) -> dict:
    days = _days_to_expiry(expiry)
    premium_total = round(premium_per_share * 100 * contracts, 2)
    actual_cost = round(strike_price - premium_per_share, 2)
    breakeven = actual_cost
    margin_required = round(strike_price * 100 * contracts, 2)
    annual_return = _annualized_return(premium_total, margin_required, days)

    # Prerequisite gate
    gate_pass = abcd_pass
    gate_note = "✅ ABCD 全通過" if gate_pass else "❌ 必須先完成 A（水平配置）B（垂直配置）C（挑選好公司）D（估值）"

    # Budget check
    budget_ok = True
    budget_note = ""
    if per_batch_budget:
        if margin_required > per_batch_budget * 3:
            budget_ok = False
            budget_note = f"⚠ 保證金 ${margin_required:,.0f} 超過 3 個批次預算 ${per_batch_budget*3:,.0f}"
        else:
            budget_note = f"✅ 保證金 ${margin_required:,.0f} 在 3 個批次預算內"

    # Check if breakeven aligns with vertical allocation
    vertical_note = ""
    if vertical_batches:
        matching = [b for b in vertical_batches if b.get("target_price", 0) >= breakeven * 0.98]
        if matching:
            vertical_note = f"✅ 損益平衡 ${breakeven} 對應垂直配置第 {matching[0]['batch']} 批次"
        else:
            vertical_note = f"⚠ 損益平衡 ${breakeven} 低於所有垂直配置目標價，請確認風險"

    # Naked call check (N/A for put)
    naked_risk = "N/A（Sell Put 不需要持有股票）"

    return {
        "strategy": "Sell Put",
        "ticker": ticker.upper(),
        "strike_price": strike_price,
        "premium_per_share": premium_per_share,
        "expiry": expiry,
        "days_to_expiry": days,
        "contracts": contracts,
        "premium_total": premium_total,
        "actual_cost": actual_cost,
        "breakeven": breakeven,
        "margin_required": margin_required,
        "annualized_return_pct": annual_return,
        "target_return_note": "課程建議瞄準 300 天以上，年化 10% 左右",
        "checks": {
            "prerequisite_abcd": {"pass": gate_pass, "note": gate_note},
            "budget_within_allocation": {"pass": budget_ok, "note": budget_note},
            "vertical_alignment": {"note": vertical_note},
            "naked_call_risk": naked_risk,
        },
        "data_note": "權利金為使用者手動輸入，非即時市場報價",
        "confidence": "user_input",
        "golden_rules": [
            "只針對精挑好公司（ABCD 通過）",
            "不超過配置預算（配置為王）",
            "只在交易深度夠大的市場操作",
        ],
    }


def sell_call(
    ticker: str,
    strike_price: float,
    premium_per_share: float,
    expiry: str,
    contracts: int = 1,
    purchase_cost_per_share: float | None = None,
    shares_held: int = 0,
    abcd_pass: bool = False,
) -> dict:
    days = _days_to_expiry(expiry)
    shares_needed = contracts * 100
    naked_risk = shares_held < shares_needed

    premium_total = round(premium_per_share * 100 * contracts, 2)
    days = _days_to_expiry(expiry)

    if purchase_cost_per_share:
        profit_if_executed = round(
            (strike_price - purchase_cost_per_share + premium_per_share) * 100 * contracts, 2
        )
        total_cost = round(purchase_cost_per_share * 100 * contracts, 2)
        annual_return = _annualized_return(profit_if_executed, total_cost, days)
    else:
        profit_if_executed = None
        annual_return = None

    return {
        "strategy": "Sell Call",
        "ticker": ticker.upper(),
        "strike_price": strike_price,
        "premium_per_share": premium_per_share,
        "expiry": expiry,
        "days_to_expiry": days,
        "contracts": contracts,
        "premium_total": premium_total,
        "profit_if_executed": profit_if_executed,
        "annualized_return_pct": annual_return,
        "checks": {
            "naked_call_risk": {
                "pass": not naked_risk,
                "note": (
                    f"✅ 持有 {shares_held} 股 ≥ 需求 {shares_needed} 股"
                    if not naked_risk
                    else f"❌ Naked Call 警告：持有 {shares_held} 股 < 需求 {shares_needed} 股。禁止執行！"
                ),
            },
            "prerequisite_abcd": {"pass": abcd_pass},
        },
        "data_note": "權利金為使用者手動輸入，非即時市場報價",
        "confidence": "user_input",
        "warning": "❌ 禁止在無持股情況下執行 Sell Call（Naked Call 風險無上限）" if naked_risk else None,
    }
