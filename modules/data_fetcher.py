"""
M7 DataFetcher — SEC EDGAR (primary) + Yahoo Finance (market price)
SEC EDGAR API: https://data.sec.gov/api/xbrl/companyfacts/{CIK}.json
"""

import httpx
import yfinance as yf
from functools import lru_cache
from typing import Optional
import re

SEC_HEADERS = {"User-Agent": "JackieAgent contact@jackietseng.com"}
SEC_BASE = "https://data.sec.gov"
EDGAR_SEARCH = "https://efts.sec.gov/LATEST/search-index?q=%22{ticker}%22&dateRange=custom&startdt=2000-01-01&enddt=2030-01-01&forms=10-K"


# ──────────────────────────────────────────────
# CIK lookup
# ──────────────────────────────────────────────

_TICKER_CIK_CACHE: dict = {}

async def get_cik(ticker: str) -> str:
    ticker = ticker.upper()
    if ticker in _TICKER_CIK_CACHE:
        return _TICKER_CIK_CACHE[ticker]

    async with httpx.AsyncClient(headers=SEC_HEADERS, timeout=15) as client:
        r = await client.get("https://www.sec.gov/files/company_tickers.json")
        r.raise_for_status()
        data = r.json()

    for _, entry in data.items():
        if entry["ticker"].upper() == ticker:
            cik = str(entry["cik_str"]).zfill(10)
            _TICKER_CIK_CACHE[ticker] = cik
            return cik

    raise ValueError(f"Ticker {ticker} not found in SEC EDGAR")


# ──────────────────────────────────────────────
# Company facts (XBRL)
# ──────────────────────────────────────────────

_FACTS_CACHE: dict = {}

async def get_company_facts(cik: str) -> dict:
    if cik in _FACTS_CACHE:
        return _FACTS_CACHE[cik]

    async with httpx.AsyncClient(headers=SEC_HEADERS, timeout=30) as client:
        r = await client.get(f"{SEC_BASE}/api/xbrl/companyfacts/CIK{cik}.json")
        r.raise_for_status()
        data = r.json()

    _FACTS_CACHE[cik] = data
    return data


# ──────────────────────────────────────────────
# Extract annual values for a concept
# ──────────────────────────────────────────────

def _extract_balance(facts: dict, *concept_keys: str, n_years: int = 6) -> dict[int, float]:
    """Extract balance-sheet (point-in-time) entries — no start date required."""
    gaap = facts.get("facts", {}).get("us-gaap", {})
    combined: dict[int, float] = {}
    filed_map: dict[int, str] = {}

    for key in concept_keys:
        entries = gaap.get(key, {}).get("units", {}).get("USD", [])
        for e in entries:
            if e.get("form") not in ("10-K", "20-F"):
                continue
            end = e.get("end", "")
            filed = e.get("filed", "")
            val = e.get("val")
            if not end or val is None:
                continue
            year_m = re.match(r"(\d{4})-", end)
            if not year_m:
                continue
            yr = int(year_m.group(1))
            if yr not in combined or filed > filed_map.get(yr, ""):
                combined[yr] = float(val)
                filed_map[yr] = filed

    if not combined:
        return {}
    sorted_years = sorted(combined.keys(), reverse=True)[:n_years]
    return {y: combined[y] for y in sorted(sorted_years)}


def _extract_from_concept(gaap: dict, key: str, unit: str = "USD") -> dict[int, float]:
    """Extract annual 10-K entries for a single concept key."""
    from datetime import date as _date

    unit_data = gaap.get(key, {}).get("units", {})
    entries = unit_data.get(unit) or unit_data.get("USD/shares") or []

    annual: dict[int, float] = {}
    filed_map: dict[int, str] = {}

    for e in entries:
        val = e.get("val")
        if val is None:
            continue
        form = e.get("form", "")
        if form not in ("10-K", "20-F"):
            continue
        start = e.get("start", "")
        end = e.get("end", "")
        filed = e.get("filed", "")
        if not start or not end:
            continue
        try:
            s = _date.fromisoformat(start)
            d = _date.fromisoformat(end)
            if (d - s).days < 300:
                continue
        except Exception:
            continue
        year_m = re.match(r"(\d{4})-", end)
        if not year_m:
            continue
        yr = int(year_m.group(1))
        if yr not in annual or filed > filed_map.get(yr, ""):
            annual[yr] = float(val)
            filed_map[yr] = filed

    return annual


def _extract_annual(facts: dict, *concept_keys: str, n_years: int = 6,
                    unit: str = "USD") -> dict[int, float]:
    """Combine data across multiple concept keys; return most-recent n_years annual values."""
    gaap = facts.get("facts", {}).get("us-gaap", {})
    combined: dict[int, float] = {}

    for key in concept_keys:
        data = _extract_from_concept(gaap, key, unit=unit)
        for yr, val in data.items():
            if yr not in combined:
                combined[yr] = val

    if not combined:
        return {}

    sorted_years = sorted(combined.keys(), reverse=True)[:n_years]
    return {y: combined[y] for y in sorted(sorted_years)}


# ──────────────────────────────────────────────
# Main financial data builder
# ──────────────────────────────────────────────

async def fetch_financials(ticker: str) -> dict:
    """Return 5-year annual financial data from SEC EDGAR."""
    cik = await get_cik(ticker)
    facts = await get_company_facts(cik)
    entity_name = facts.get("entityName", ticker)

    revenue = _extract_annual(facts,
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    )
    cogs = _extract_annual(facts,
        "CostOfGoodsAndServicesSold",
        "CostOfRevenue",
        "CostOfGoodsSold",
    )
    gross_profit = _extract_annual(facts, "GrossProfit")
    operating_income = _extract_annual(facts,
        "OperatingIncomeLoss",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    )
    net_income = _extract_annual(facts, "NetIncomeLoss", "ProfitLoss")
    eps = _extract_annual(facts,
        "EarningsPerShareDiluted",
        "EarningsPerShareBasic",
        unit="USD/shares",
    )
    operating_cf = _extract_annual(facts,
        "NetCashProvidedByUsedInOperatingActivities",
    )
    investing_cf = _extract_annual(facts,
        "NetCashProvidedByUsedInInvestingActivities",
    )
    financing_cf = _extract_annual(facts,
        "NetCashProvidedByUsedInFinancingActivities",
    )
    capex = _extract_annual(facts,
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsForCapitalImprovements",
        "CapitalExpendituresIncurredButNotYetPaid",
    )
    # Balance sheet items (point-in-time, no start date)
    long_term_debt = _extract_balance(facts,
        "LongTermDebt",
        "LongTermDebtNoncurrent",
    )
    total_debt = _extract_balance(facts,
        "DebtAndCapitalLeaseObligations",
        "LongTermDebtAndCapitalLeaseObligations",
        "LongTermDebt",
    )
    equity = _extract_balance(facts,
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    )
    current_assets = _extract_balance(facts, "AssetsCurrent")
    current_liabilities = _extract_balance(facts, "LiabilitiesCurrent")
    total_assets = _extract_balance(facts, "Assets")

    # Compute gross profit rate if gross_profit not directly available
    gross_margin_rate: dict[int, float] = {}
    for year in revenue:
        gp = gross_profit.get(year)
        if gp is None and year in cogs:
            gp = revenue[year] - cogs[year]
        if gp is not None and revenue[year] != 0:
            gross_margin_rate[year] = gp / revenue[year] * 100

    # Compute free cash flow
    free_cf: dict[int, float] = {}
    for year in operating_cf:
        capex_val = capex.get(year, 0)
        free_cf[year] = operating_cf[year] - abs(capex_val)

    # Effective D/E (prefer total_debt, fallback to long_term_debt)
    effective_debt = total_debt if total_debt else long_term_debt

    return {
        "ticker": ticker,
        "cik": cik,
        "entity_name": entity_name,
        "source": "sec_edgar",
        "revenue": revenue,
        "gross_margin_rate": gross_margin_rate,
        "gross_profit": gross_profit,
        "operating_income": operating_income,
        "net_income": net_income,
        "eps": eps,
        "operating_cf": operating_cf,
        "investing_cf": investing_cf,
        "financing_cf": financing_cf,
        "capex": capex,
        "free_cf": free_cf,
        "long_term_debt": long_term_debt,
        "total_debt": effective_debt,
        "equity": equity,
        "current_assets": current_assets,
        "current_liabilities": current_liabilities,
        "total_assets": total_assets,
    }


# ──────────────────────────────────────────────
# Yahoo Finance — market price
# ──────────────────────────────────────────────

def fetch_market_price(ticker: str) -> dict:
    try:
        t = yf.Ticker(ticker)
        info = t.fast_info
        price = getattr(info, "last_price", None) or getattr(info, "regularMarketPrice", None)
        if price is None:
            hist = t.history(period="1d")
            price = float(hist["Close"].iloc[-1]) if not hist.empty else None
        return {
            "current_price": price,
            "source": "yahoo_finance",
            "delay_note": "可能 15–20 分鐘延遲",
            "confidence": "medium",
        }
    except Exception as e:
        return {
            "current_price": None,
            "source": "yahoo_finance",
            "error": str(e),
            "confidence": "unknown",
        }


def fetch_pe_history(ticker: str) -> dict:
    """Return trailing PE as proxy for current PE; historical avg requires external source."""
    try:
        t = yf.Ticker(ticker)
        info = t.info
        trailing_pe = info.get("trailingPE")
        forward_pe = info.get("forwardPE")
        eps_ttm = info.get("trailingEps")
        return {
            "trailing_pe": trailing_pe,
            "forward_pe": forward_pe,
            "eps_ttm": eps_ttm,
            "source": "yahoo_finance",
            "note": "歷史均值 PE 需使用者手動從 Macrotrends 查詢",
            "confidence": "medium",
        }
    except Exception as e:
        return {"error": str(e), "source": "yahoo_finance"}
