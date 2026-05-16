"""M2 VerticalAllocator — 分批進場計算"""


def calculate_vertical(
    per_stock_budget: float,
    fair_value: float,
    current_price: float,
    batch_count: int = 5,
    safety_margin_steps: list[float] | None = None,
) -> dict:
    if safety_margin_steps is None:
        safety_margin_steps = [10, 20, 25, 30, 40] if batch_count == 5 else [10, 20, 35]

    if len(safety_margin_steps) != batch_count:
        safety_margin_steps = safety_margin_steps[:batch_count]
        while len(safety_margin_steps) < batch_count:
            safety_margin_steps.append(safety_margin_steps[-1] + 10)

    # Batch amount distribution
    if batch_count == 5:
        ratios = [0.20, 0.20, 0.20, 0.20, 0.20]
    elif batch_count == 3:
        ratios = [0.30, 0.30, 0.40]
    else:
        ratios = [1 / batch_count] * batch_count

    current_safety_margin = round((fair_value - current_price) / fair_value * 100, 2)

    batches = []
    for i, (sm, ratio) in enumerate(zip(safety_margin_steps, ratios), start=1):
        target_price = round(fair_value * (1 - sm / 100), 2)
        amount = round(per_stock_budget * ratio)
        shares_approx = int(amount / target_price) if target_price > 0 else 0

        if current_price <= target_price:
            status = "可買入"
            buyable = True
        elif current_price <= target_price * 1.02:
            status = "接近觸及"
            buyable = True
        else:
            status = "等待中"
            buyable = False

        batches.append({
            "batch": i,
            "safety_margin_pct": sm,
            "target_price": target_price,
            "amount_usd": amount,
            "shares_approx": shares_approx,
            "status": status,
            "buyable": buyable,
        })

    buyable_batches = [b for b in batches if b["buyable"]]
    deployed = sum(b["amount_usd"] for b in buyable_batches)
    remaining = per_stock_budget - deployed

    return {
        "per_stock_budget": per_stock_budget,
        "fair_value": fair_value,
        "current_price": current_price,
        "current_safety_margin_pct": current_safety_margin,
        "current_verdict": "低估" if current_safety_margin > 0 else "高估",
        "batches": batches,
        "buyable_batches_count": len(buyable_batches),
        "deployed_amount": deployed,
        "remaining_cash": remaining,
        "safety_margin_formula": "(估值 - 市價) / 估值 × 100%",
        "options_note": f"剩餘 ${remaining:,.0f} 可考慮 Sell Put 策略（E 步驟）",
    }


def calculate_horizontal(
    total_investment: float,
    user_age: int = 35,
    manual_aggressive_pct: float | None = None,
    manual_defensive_pct: float | None = None,
    manual_lottery_pct: float | None = None,
) -> dict:
    if manual_aggressive_pct is not None:
        agg = manual_aggressive_pct
        dfd = manual_defensive_pct or 0
        lot = manual_lottery_pct or (100 - agg - dfd)
    elif user_age <= 25:
        agg, dfd, lot = 85, 0, 15
    elif user_age <= 35:
        agg, dfd, lot = 80, 10, 10
    elif user_age <= 45:
        agg, dfd, lot = 70, 20, 10
    elif user_age <= 55:
        agg, dfd, lot = 65, 30, 5
    elif user_age <= 65:
        agg, dfd, lot = 15, 60, 5
    elif user_age <= 75:
        agg, dfd, lot = 5, 70, 5
    else:
        agg, dfd, lot = 0, 60, 0

    agg_amount = total_investment * agg / 100
    dfd_amount = total_investment * dfd / 100
    lot_amount = total_investment * lot / 100

    # Stock count by aggressive capital size
    if agg_amount < 5000:
        stock_count = 2
    elif agg_amount < 30000:
        stock_count = 4
    elif agg_amount < 50000:
        stock_count = 6
    elif agg_amount < 100000:
        stock_count = 8
    else:
        stock_count = 10

    per_stock = round(agg_amount / stock_count) if stock_count else 0

    return {
        "total_investment": total_investment,
        "user_age": user_age,
        "allocation": {
            "aggressive_pct": agg,
            "aggressive_amount": round(agg_amount),
            "defensive_pct": dfd,
            "defensive_amount": round(dfd_amount),
            "lottery_pct": lot,
            "lottery_amount": round(lot_amount),
        },
        "suggested_stock_count": stock_count,
        "per_stock_budget": per_stock,
        "safety_bucket_note": "保障型（緊急備用金 + 保險）需另外計算，不含在投資金額內",
        "defensive_note": "防守型建議：SPY / QQQ 定期不定額",
        "lottery_max_pct": 15,
    }
