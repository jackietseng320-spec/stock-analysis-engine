"""
Morningstar 公允價值動態抓取模組（via Firstrade PDF reports）

流程：
1. Firecrawl search → site:invest.firstrade.com {ticker} fair value
2. 從搜尋 snippet 直接提取公允價值（最快路徑）
3. 若 snippet 無數字 → 下載 PDF 解析（fallback）
4. 取最新日期報告，記憶體 cache 7 天
"""

from __future__ import annotations
import os
import re
import time
import logging
import requests

logger = logging.getLogger(__name__)

_CACHE: dict[str, dict] = {}
_CACHE_TTL = 7 * 24 * 3600  # 7 days

# Morningstar 標準句型「wide-moat [Company]」公司關鍵字
_TICKER_KEYWORDS: dict[str, list[str]] = {
    "AAPL": ["apple"],
    "MSFT": ["microsoft"],
    "NVDA": ["nvidia"],
    "META": ["meta"],
    "GOOGL": ["alphabet", "google"],
    "GOOG": ["alphabet", "google"],
    "AMZN": ["amazon"],
    "TSLA": ["tesla"],
    "TSM": ["taiwan semiconductor", "tsmc"],
    "AVGO": ["broadcom"],
    "JPM": ["jpmorgan", "jp morgan"],
    "V": ["visa"],
    "MA": ["mastercard"],
    "JNJ": ["johnson"],
    "WMT": ["walmart"],
    "XOM": ["exxon"],
    "BRKB": ["berkshire"],
    "BRKA": ["berkshire"],
    "UNH": ["unitedhealth"],
    "LLY": ["eli lilly", "lilly"],
    "HD": ["home depot"],
    "MRK": ["merck"],
    "ABBV": ["abbvie"],
    "COST": ["costco"],
    "PEP": ["pepsico", "pepsi"],
    "KO": ["coca-cola", "coca cola"],
    "NKE": ["nike"],
    "DIS": ["disney"],
    "NFLX": ["netflix"],
    "ADBE": ["adobe"],
    "CRM": ["salesforce"],
    "ORCL": ["oracle"],
    "INTC": ["intel"],
    "AMD": ["advanced micro", "amd"],
    "QCOM": ["qualcomm"],
}


def _firecrawl_headers() -> dict:
    key = os.environ.get("FIRECRAWL_API_KEY", "")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _extract_fair_value_from_text(text: str) -> float | None:
    """從文字提取 Morningstar 公允價值金額（支援 snippet 和 PDF 全文）。"""
    patterns = [
        r'our\s+\$(\d{2,5}(?:,\d{3})?(?:\.\d+)?)\s+fair value estimate',
        r'\$(\d{2,5}(?:,\d{3})?(?:\.\d+)?)\s+fair value estimate',
        r'fair value estimate.*?to\s+\$(\d{2,5}(?:,\d{3})?(?:\.\d+)?)',
        r'fair value.*?\$(\d{2,5}(?:,\d{3})?(?:\.\d+)?)',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = float(m.group(1).replace(",", ""))
            if 1 < val < 100_000:
                return val
    return None


def _scrape_pdf_fair_value(pdf_url: str, ticker: str) -> float | None:
    """直接下載 Firstrade PDF 並提取公允價值（snippet 無數字時使用）。"""
    # Strip UTM parameters to get clean PDF URL
    clean_url = pdf_url.split("?")[0]
    try:
        resp = requests.post(
            "https://api.firecrawl.dev/v1/scrape",
            headers=_firecrawl_headers(),
            json={
                "url": clean_url,
                "formats": ["markdown"],
                "parsers": ["pdf"],
            },
            timeout=30,
        )
        if not resp.ok:
            return None
        md = resp.json().get("markdown", "") or ""
        if not md:
            return None
        # Check company is correct
        keywords = _TICKER_KEYWORDS.get(ticker, [ticker.lower()])
        if not any(kw in md[:2000].lower() for kw in keywords):
            return None
        return _extract_fair_value_from_text(md[:3000])
    except Exception as e:
        logger.warning(f"[Morningstar] PDF scrape error for {ticker}: {e}")
    return None


def get_morningstar_fair_value(ticker: str) -> dict | None:
    """
    Public entry point. Returns dict:
      {"value": float, "source": "morningstar", "confidence": "high",
       "source_url": str, "report_date": str}
    or None if unavailable.
    """
    ticker = ticker.upper()

    # Cache check
    cached = _CACHE.get(ticker)
    if cached and (time.time() - cached.get("_ts", 0)) < _CACHE_TTL:
        logger.info(f"[Morningstar] cache hit for {ticker}")
        return {k: v for k, v in cached.items() if k != "_ts"}

    if not os.environ.get("FIRECRAWL_API_KEY"):
        logger.warning("[Morningstar] FIRECRAWL_API_KEY not set, skipping")
        return None

    logger.info(f"[Morningstar] searching Firstrade reports for {ticker}...")

    keywords = _TICKER_KEYWORDS.get(ticker, [ticker.lower()])
    company_hint = keywords[0] if keywords else ticker.lower()

    try:
        resp = requests.post(
            "https://api.firecrawl.dev/v1/search",
            headers=_firecrawl_headers(),
            json={
                "query": f'site:invest.firstrade.com "{company_hint}" fair value morningstar',
                "limit": 8,
            },
            timeout=20,
        )
        if not resp.ok:
            logger.warning(f"[Morningstar] search HTTP {resp.status_code} for {ticker}")
            return None

        body = resp.json()
        raw = body.get("data", [])
        results = raw if isinstance(raw, list) else raw.get("web", [])

    except Exception as e:
        logger.warning(f"[Morningstar] search error for {ticker}: {e}")
        return None

    best = None
    best_date = ""
    pdf_candidates: list[tuple[str, str]] = []  # (date_str, url)

    for r in results:
        url = r.get("url", "")
        desc = r.get("description", "")
        desc_lower = desc.lower()

        if "invest.firstrade.com/ms/equity_reports" not in url:
            continue

        # Must mention the right company in description
        if not any(kw in desc_lower for kw in keywords):
            logger.debug(f"[Morningstar] skip mismatch for {ticker}: {desc[:80]}")
            continue

        date_m = re.search(r'_(\d{8})_RT', url)
        date_str = date_m.group(1) if date_m else "00000000"

        value = _extract_fair_value_from_text(desc)
        if value is None:
            pdf_candidates.append((date_str, url))
            continue

        if date_str > best_date:
            best_date = date_str
            best = {
                "value": value,
                "source": "morningstar",
                "source_detail": "Morningstar Equity Report via Firstrade",
                "confidence": "high",
                "source_url": url,
                "report_date": f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}",
            }

    # PDF fallback: parse the most recent matching PDF
    if best is None and pdf_candidates:
        pdf_candidates.sort(reverse=True)
        for date_str, pdf_url in pdf_candidates[:2]:
            logger.info(f"[Morningstar] trying PDF fallback for {ticker}: {pdf_url[-60:]}")
            value = _scrape_pdf_fair_value(pdf_url, ticker)
            if value:
                best = {
                    "value": value,
                    "source": "morningstar",
                    "source_detail": "Morningstar Equity Report via Firstrade (PDF)",
                    "confidence": "high",
                    "source_url": pdf_url.split("?")[0],
                    "report_date": f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}",
                }
                break

    if best:
        _CACHE[ticker] = {**best, "_ts": time.time()}
        logger.info(f"[Morningstar] {ticker} = ${best['value']} from {best['report_date']}")
        return best

    logger.info(f"[Morningstar] no result found for {ticker}")
    _CACHE[ticker] = {"value": None, "_ts": time.time()}
    return None
