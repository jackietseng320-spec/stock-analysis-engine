"""
Morningstar 公允價值動態抓取模組

流程：
1. Firecrawl search → 找最新 Morningstar 股票文章
2. Firecrawl scrape → 從文章提取 Fair Value Estimate
3. 記憶體 cache 7 天，避免重複呼叫
"""

from __future__ import annotations
import os
import time
import re
import logging
import requests

logger = logging.getLogger(__name__)

_CACHE: dict[str, dict] = {}
_CACHE_TTL = 7 * 24 * 3600  # 7 days


def _firecrawl_headers() -> dict:
    key = os.environ.get("FIRECRAWL_API_KEY", "")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _search_morningstar_article(ticker: str) -> str | None:
    """Search for the latest Morningstar article URL for a ticker."""
    try:
        resp = requests.post(
            "https://api.firecrawl.dev/v1/search",
            headers=_firecrawl_headers(),
            json={
                "query": f"site:morningstar.com/stocks {ticker} fair value estimate earnings",
                "limit": 5,
            },
            timeout=15,
        )
        if not resp.ok:
            return None
        results = resp.json().get("data", {}).get("web", [])
        for r in results:
            url = r.get("url", "")
            # Prefer article pages over quote/profile pages
            if (
                "morningstar.com/stocks/" in url
                and "quote" not in url
                and "profile" not in url
                and "financials" not in url
                and "valuation" not in url
            ):
                # Quick check: description mentions fair value
                desc = r.get("description", "").lower()
                if "fair value" in desc or "undervalued" in desc or "overvalued" in desc:
                    return url
        # Fallback: return first stocks URL regardless
        for r in results:
            url = r.get("url", "")
            if "morningstar.com/stocks/" in url and "quote" not in url:
                return url
    except Exception as e:
        logger.warning(f"[Morningstar] search error for {ticker}: {e}")
    return None


def _scrape_fair_value(ticker: str, url: str) -> float | None:
    """Scrape a Morningstar article and extract the Fair Value Estimate."""
    try:
        resp = requests.post(
            "https://api.firecrawl.dev/v1/scrape",
            headers=_firecrawl_headers(),
            json={
                "url": url,
                "formats": ["json"],
                "jsonOptions": {
                    "prompt": (
                        f"Find the Morningstar Fair Value Estimate (公允價值) dollar amount for {ticker} stock. "
                        "Return a JSON with field 'fair_value' (number only, e.g. 600) and 'date' (publication date string). "
                        "If no fair value is found, return null."
                    )
                },
                "proxy": "stealth",
                "waitFor": 6000,
            },
            timeout=35,
        )
        if not resp.ok:
            return None
        data = resp.json().get("json") or {}
        if not data:
            return None

        # Try common field names
        raw = (
            data.get("fair_value")
            or data.get("fairValue")
            or data.get("fair_value_estimate")
            or data.get("fairValueEstimate")
        )
        if raw is None:
            return None

        val = float(str(raw).replace(",", ""))
        # Sanity check: reject implausible values
        if val <= 0 or val > 100_000:
            return None
        return val

    except Exception as e:
        logger.warning(f"[Morningstar] scrape error for {ticker} @ {url}: {e}")
    return None


def get_morningstar_fair_value(ticker: str) -> dict | None:
    """
    Public entry point. Returns dict:
      {"value": float, "source": "morningstar", "confidence": "high", "source_url": str}
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

    logger.info(f"[Morningstar] fetching for {ticker}...")

    # Step 1: Find article URL
    url = _search_morningstar_article(ticker)
    if not url:
        logger.info(f"[Morningstar] no article found for {ticker}")
        _CACHE[ticker] = {"value": None, "_ts": time.time()}
        return None

    # Step 2: Extract fair value
    value = _scrape_fair_value(ticker, url)
    if value is None:
        logger.info(f"[Morningstar] fair value not found in article for {ticker}")
        _CACHE[ticker] = {"value": None, "_ts": time.time()}
        return None

    result = {
        "value": value,
        "source": "morningstar",
        "confidence": "high",
        "source_url": url,
    }
    _CACHE[ticker] = {**result, "_ts": time.time()}
    logger.info(f"[Morningstar] {ticker} = ${value} from {url}")
    return result
