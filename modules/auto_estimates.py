"""M10 AutoEstimates — 自動計算 ROIC、WACC、歷史均值 PE、同業資產週轉率"""

# Morningstar 公允價值查找表（手動維護，最高優先級）
# 格式：ticker -> {"value": float, "date": "YYYY-MM-DD", "article": "..."}
MORNINGSTAR_FAIR_VALUES: dict[str, dict] = {
    "MSFT": {"value": 600.0, "date": "2026-03-01", "note": "Wide-moat; multiple 2026 articles maintain $600"},
    "NVDA": {"value": 260.0, "date": "2026-03-17", "note": "Raising FVE on agentic AI / $1T GTC forecast"},
    "META": {"value": 850.0, "date": "2026-04-29", "note": "Ad sales growth accelerates even as AI costs mount"},
    "TSM":  {"value": 428.0, "date": "2026-04-16", "note": "TWD 2,700 / USD 428; refining guidance amid strong AI demand"},
    "2330": {"value": 428.0, "date": "2026-04-16", "note": "Same as TSM ADR"},
}

# 行業資產週轉率參考值（來源：Damodaran 行業平均）
SECTOR_ASSET_TURNOVER = {
    "Technology": 0.60,
    "Communication Services": 0.55,
    "Consumer Cyclical": 1.10,
    "Consumer Defensive": 0.90,
    "Healthcare": 0.55,
    "Financials": 0.08,
    "Financial Services": 0.08,
    "Industrials": 0.75,
    "Basic Materials": 0.65,
    "Energy": 0.45,
    "Utilities": 0.30,
    "Real Estate": 0.15,
}

# 行業歷史均值 PE 參考值（來源：Damodaran）
SECTOR_PE_AVG = {
    "Technology": 30.0,
    "Communication Services": 22.0,
    "Consumer Cyclical": 25.0,
    "Consumer Defensive": 22.0,
    "Healthcare": 22.0,
    "Financials": 14.0,
    "Financial Services": 14.0,
    "Industrials": 20.0,
    "Basic Materials": 16.0,
    "Energy": 14.0,
    "Utilities": 18.0,
    "Real Estate": 30.0,
}

RISK_FREE_RATE = 0.045   # 美國 10 年期國債約 4.5%
EQUITY_RISK_PREMIUM = 0.055  # 股權風險溢酬約 5.5%
DEFAULT_TAX_RATE = 0.21  # 美國企業稅率


def calculate_roic(financials: dict) -> dict:
    """
    ROIC = Net Income / (Equity + Long-term Debt)
    簡化版（不扣現金），適合快速估算。
    取最近一年數據。
    """
    net_income = financials.get("net_income", {})
    equity = financials.get("equity", {})
    lt_debt = financials.get("total_debt", {})

    if not net_income or not equity:
        return {"roic_pct": None, "note": "財報數據不足，無法計算 ROIC", "confidence": "unknown"}

    latest_year = max(net_income.keys())
    ni = net_income.get(latest_year)
    eq = equity.get(latest_year) or equity.get(max(equity.keys()))
    debt = lt_debt.get(latest_year, 0) if lt_debt else 0

    invested_capital = eq + debt
    if not invested_capital or invested_capital <= 0:
        return {"roic_pct": None, "note": "投入資本為零或負值", "confidence": "unknown"}

    roic = round(ni / invested_capital * 100, 2)
    return {
        "roic_pct": roic,
        "year": latest_year,
        "formula": f"Net Income {ni:,.0f} / (Equity {eq:,.0f} + LT Debt {debt:,.0f}) × 100",
        "source": "sec_edgar_auto",
        "confidence": "medium",
        "note": "簡化版 ROIC，未扣除現金及非核心資產",
    }


def estimate_wacc(yahoo_data: dict, financials: dict) -> dict:
    """
    WACC = We × Ce + Wd × Cd × (1 - T)
    Ce = Rf + Beta × ERP  (CAPM)
    Cd = Interest Expense / Total Debt
    """
    beta = yahoo_data.get("beta")
    market_cap = yahoo_data.get("market_cap")
    total_debt_yahoo = yahoo_data.get("total_debt") or 0
    interest_expense = yahoo_data.get("interest_expense") or 0
    tax_rate = yahoo_data.get("tax_rate") or DEFAULT_TAX_RATE

    if not beta or not market_cap:
        return {
            "wacc_pct": None,
            "note": "Beta 或市值數據缺失，無法計算 WACC",
            "confidence": "unknown",
        }

    # Cost of equity (CAPM)
    cost_of_equity = RISK_FREE_RATE + beta * EQUITY_RISK_PREMIUM

    # Capital structure weights
    total_capital = market_cap + total_debt_yahoo
    we = market_cap / total_capital
    wd = total_debt_yahoo / total_capital if total_capital > 0 else 0

    # Cost of debt
    if total_debt_yahoo > 0 and interest_expense and interest_expense < 0:
        cost_of_debt = abs(interest_expense) / total_debt_yahoo
    elif total_debt_yahoo > 0 and interest_expense and interest_expense > 0:
        cost_of_debt = interest_expense / total_debt_yahoo
    else:
        cost_of_debt = 0.05  # 預設 5%

    wacc = round((we * cost_of_equity + wd * cost_of_debt * (1 - tax_rate)) * 100, 2)
    ce_pct = round(cost_of_equity * 100, 2)
    cd_pct = round(cost_of_debt * 100, 2)

    return {
        "wacc_pct": wacc,
        "cost_of_equity_pct": ce_pct,
        "cost_of_debt_pct": cd_pct,
        "beta": beta,
        "weight_equity": round(we * 100, 1),
        "weight_debt": round(wd * 100, 1),
        "formula": f"WACC = {we:.1%}×{ce_pct}% + {wd:.1%}×{cd_pct}%×(1-{tax_rate:.0%})",
        "source": "capm_auto",
        "confidence": "medium",
        "note": "CAPM 自動估算，建議對照 Gurufocus 確認",
    }


def estimate_pe_hist_avg(yahoo_data: dict, financials: dict, ticker: str = "") -> dict:
    """
    歷史均值 PE（優先順序）：
    1. 從 Yahoo Finance 5 年股價歷史 + SEC EDGAR EPS 實際計算
    2. 若數據不足，退用 Damodaran 行業均值
    """
    import yfinance as yf

    sector = yahoo_data.get("sector", "")
    trailing_pe = yahoo_data.get("trailing_pe")
    eps_dict = financials.get("eps", {})

    # Method 1: 實際計算（Yahoo 年均價 + SEC EPS）
    if ticker and eps_dict and len(eps_dict) >= 3:
        try:
            hist = yf.Ticker(ticker).history(period="5y", interval="1mo")
            if not hist.empty:
                yearly_pe = {}
                for year, eps in eps_dict.items():
                    if eps and eps > 0:
                        year_prices = hist[hist.index.year == year]["Close"]
                        if not year_prices.empty:
                            avg_price = float(year_prices.mean())
                            pe = avg_price / eps
                            if 5 < pe < 200:
                                yearly_pe[year] = round(pe, 1)

                if len(yearly_pe) >= 3:
                    avg_pe = round(sum(yearly_pe.values()) / len(yearly_pe), 1)
                    return {
                        "pe_hist_avg": avg_pe,
                        "method": f"實際歷史均值 PE（{len(yearly_pe)} 年）",
                        "yearly_pe": yearly_pe,
                        "trailing_pe": trailing_pe,
                        "source": "yahoo_price_x_sec_eps",
                        "source_detail": "Yahoo Finance 月均價 × SEC EDGAR EPS",
                        "confidence": "high",
                    }
        except Exception:
            pass

    # Method 2: Damodaran 行業均值（備選）
    sector_pe = SECTOR_PE_AVG.get(sector)
    if sector_pe:
        return {
            "pe_hist_avg": sector_pe,
            "method": f"Damodaran 行業均值 PE（{sector}）",
            "trailing_pe": trailing_pe,
            "source": "damodaran_sector_avg",
            "source_detail": "NYU Damodaran 行業年度資料（全球投行引用標準）",
            "confidence": "medium",
            "note": "個股歷史 PE 數據不足，改用行業均值",
        }

    return {
        "pe_hist_avg": trailing_pe,
        "method": "當前 Trailing PE（無歷史數據）",
        "source": "yahoo_finance",
        "confidence": "low",
        "note": "無法計算歷史均值，以當前 PE 代替",
    }


def estimate_industry_asset_turnover(yahoo_data: dict) -> dict:
    """依行業返回同業資產週轉率均值。"""
    sector = yahoo_data.get("sector", "")
    avg = SECTOR_ASSET_TURNOVER.get(sector)

    if avg:
        return {
            "industry_asset_turnover_avg": avg,
            "sector": sector,
            "source": "damodaran_sector_avg",
            "confidence": "medium",
            "note": f"來源：Damodaran {sector} 行業均值",
        }
    return {
        "industry_asset_turnover_avg": 0.70,
        "sector": sector or "unknown",
        "source": "default_fallback",
        "confidence": "low",
        "note": "無行業分類，使用通用預設值 0.70",
    }


def estimate_fair_value(yahoo_data: dict, pe_hist_info: dict, ticker: str = "") -> dict:
    """
    公允價值自動估算（優先順序）：
    0. Morningstar 公允價值查找表（最高優先）
    1. 分析師共識目標價（Yahoo）
    2. 歷史均值 PE × EPS TTM
    """
    estimates = []
    ticker_upper = (ticker or yahoo_data.get("ticker", "")).upper()

    # Method 0: Morningstar 查找表（最高優先）
    ms = MORNINGSTAR_FAIR_VALUES.get(ticker_upper)
    if ms:
        estimates.append({
            "method": f"Morningstar 公允價值（{ms['date']}）",
            "value": ms["value"],
            "source": "morningstar",
            "confidence": "high",
            "priority": 0,
            "note": ms.get("note", ""),
        })

    # Method 1: 分析師共識目標價
    analyst_mean = yahoo_data.get("analyst_target_mean")
    analyst_count = yahoo_data.get("analyst_count", 0)
    analyst_low = yahoo_data.get("analyst_target_low")
    analyst_high = yahoo_data.get("analyst_target_high")

    if analyst_mean and analyst_count and analyst_count >= 3:
        estimates.append({
            "method": f"分析師共識目標價（{analyst_count} 位分析師）",
            "value": round(analyst_mean, 2),
            "range": f"${analyst_low:.0f} – ${analyst_high:.0f}" if analyst_low and analyst_high else None,
            "source": "yahoo_analyst_consensus",
            "confidence": "medium",
            "priority": 1,
        })

    # Method 2: 歷史均值 PE × EPS TTM
    eps_ttm = yahoo_data.get("eps_ttm")
    pe_avg = pe_hist_info.get("pe_hist_avg")
    if eps_ttm and pe_avg and eps_ttm > 0:
        pe_estimate = round(eps_ttm * pe_avg, 2)
        estimates.append({
            "method": f"歷史均值 PE × EPS（{pe_avg} × ${eps_ttm:.2f}）",
            "value": pe_estimate,
            "source": "pe_auto_estimate",
            "confidence": "low",
            "priority": 2,
            "warning": "對高成長股可能低估，建議參考分析師目標價",
        })

    if not estimates:
        return {
            "auto_fair_value": None,
            "estimates": [],
            "note": "無法自動估算公允價值，請手動輸入",
        }

    primary = min(estimates, key=lambda x: x["priority"])
    return {
        "auto_fair_value": primary["value"],
        "primary_method": primary["method"],
        "primary_source": primary["source"],
        "primary_confidence": primary["confidence"],
        "estimates": estimates,
        "recommendation": primary.get("range"),
    }
