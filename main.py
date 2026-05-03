"""
美股分析引擎 API v1.0
Architecture C: ChatGPT Custom GPT → FastAPI → SEC EDGAR + Yahoo Finance
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional
import asyncio

from modules.data_fetcher import fetch_financials, fetch_market_price, fetch_pe_history, fetch_yahoo_full
from modules.peace_calc import calculate_peace
from modules.valuation import calculate_valuation
from modules.vertical import calculate_vertical, calculate_horizontal
from modules.options_calc import sell_put, sell_call
from modules.qualitative import evaluate_qualitative, get_qualitative_template
from modules.report import generate_report
from modules.auto_estimates import (
    calculate_roic, estimate_wacc, estimate_pe_hist_avg,
    estimate_industry_asset_turnover, estimate_fair_value,
)

app = FastAPI(
    title="美股分析引擎",
    description="個人財務逆向工程 ABCDE 分析系統",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://chat.openai.com", "https://chatgpt.com"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────
# Request / Response Models
# ──────────────────────────────────────────────

class PEACERequest(BaseModel):
    ticker: str
    industry_asset_turnover_avg: Optional[float] = Field(None, description="同行資產週轉率均值（手動輸入）")
    roic: Optional[float] = Field(None, description="ROIC %（手動查詢 Gurufocus）")
    wacc: Optional[float] = Field(None, description="WACC %（手動查詢 Gurufocus）")


class ValuationRequest(BaseModel):
    ticker: str
    fair_value_manual: Optional[float] = Field(None, description="公允價值（Morningstar 等）")
    fair_value_source: str = Field("user_input", description="公允價值來源")
    eps_ttm: Optional[float] = Field(None, description="EPS TTM（留空則從 Yahoo 抓）")
    pe_hist_avg: Optional[float] = Field(None, description="歷史均值 PE（Macrotrends 手動查詢）")


class VerticalRequest(BaseModel):
    per_stock_budget: float
    fair_value: float
    current_price: float
    batch_count: int = Field(5, ge=3, le=5)
    safety_margin_steps: Optional[list[float]] = Field(None, description="安全邊際%列表，如 [0,10,20,30,50]")


class HorizontalRequest(BaseModel):
    total_investment: float
    user_age: int = 35
    manual_aggressive_pct: Optional[float] = None
    manual_defensive_pct: Optional[float] = None
    manual_lottery_pct: Optional[float] = None


class QualitativeRequest(BaseModel):
    ticker: str
    moat_scores: dict[str, str] = Field(
        default_factory=dict,
        description="{'intangible_assets':'yes','cost_advantage':'no',...}"
    )
    risk_scores: dict[str, str] = Field(
        default_factory=dict,
        description="{'regulatory':'pass','inflation':'pass',...}"
    )
    moat_evidences: Optional[dict[str, str]] = None
    risk_notes: Optional[dict[str, str]] = None


class SellPutRequest(BaseModel):
    ticker: str
    strike_price: float
    premium_per_share: float
    expiry: str = Field(..., description="YYYY-MM-DD")
    contracts: int = 1
    abcd_pass: bool = False
    per_batch_budget: Optional[float] = None
    fair_value: Optional[float] = None
    vertical_batches: Optional[list[dict]] = None


class SellCallRequest(BaseModel):
    ticker: str
    strike_price: float
    premium_per_share: float
    expiry: str = Field(..., description="YYYY-MM-DD")
    contracts: int = 1
    purchase_cost_per_share: Optional[float] = None
    shares_held: int = 0
    abcd_pass: bool = False


class FullAnalysisRequest(BaseModel):
    ticker: str
    total_investment: Optional[float] = None
    user_age: int = 35
    fair_value_manual: Optional[float] = None
    fair_value_source: str = "user_input"
    pe_hist_avg: Optional[float] = None
    industry_asset_turnover_avg: Optional[float] = None
    roic: Optional[float] = None
    wacc: Optional[float] = None
    batch_count: int = 5
    safety_margin_steps: Optional[list[float]] = None
    moat_scores: dict[str, str] = Field(default_factory=dict)
    risk_scores: dict[str, str] = Field(default_factory=dict)
    moat_evidences: Optional[dict[str, str]] = None
    risk_notes: Optional[dict[str, str]] = None


# ──────────────────────────────────────────────
# Health
# ──────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


# ──────────────────────────────────────────────
# D — PEACE (Quantitative Analysis)
# ──────────────────────────────────────────────

@app.post("/peace")
async def peace_endpoint(req: PEACERequest):
    try:
        financials = await fetch_financials(req.ticker)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(502, f"SEC EDGAR 抓取失敗：{e}")

    result = calculate_peace(
        financials,
        industry_asset_turnover_avg=req.industry_asset_turnover_avg,
        roic=req.roic,
        wacc=req.wacc,
    )
    return result


# ──────────────────────────────────────────────
# D — Valuation
# ──────────────────────────────────────────────

@app.post("/valuation")
async def valuation_endpoint(req: ValuationRequest):
    price_info = fetch_market_price(req.ticker)
    current_price = price_info.get("current_price")
    if not current_price:
        raise HTTPException(502, "無法取得市價，請稍後再試或手動輸入")

    eps_ttm = req.eps_ttm
    if not eps_ttm:
        pe_info = fetch_pe_history(req.ticker)
        eps_ttm = pe_info.get("eps_ttm")

    return calculate_valuation(
        current_price=current_price,
        fair_value_manual=req.fair_value_manual,
        fair_value_source=req.fair_value_source,
        eps_ttm=eps_ttm,
        pe_hist_avg=req.pe_hist_avg,
    )


# ──────────────────────────────────────────────
# A + B — Allocation
# ──────────────────────────────────────────────

@app.post("/allocation/horizontal")
def horizontal_endpoint(req: HorizontalRequest):
    return calculate_horizontal(
        total_investment=req.total_investment,
        user_age=req.user_age,
        manual_aggressive_pct=req.manual_aggressive_pct,
        manual_defensive_pct=req.manual_defensive_pct,
        manual_lottery_pct=req.manual_lottery_pct,
    )


@app.post("/allocation/vertical")
def vertical_endpoint(req: VerticalRequest):
    return calculate_vertical(
        per_stock_budget=req.per_stock_budget,
        fair_value=req.fair_value,
        current_price=req.current_price,
        batch_count=req.batch_count,
        safety_margin_steps=req.safety_margin_steps,
    )


# ──────────────────────────────────────────────
# C — Qualitative
# ──────────────────────────────────────────────

@app.get("/qualitative/template/{ticker}")
def qualitative_template(ticker: str):
    return get_qualitative_template(ticker)


@app.post("/qualitative")
def qualitative_endpoint(req: QualitativeRequest):
    return evaluate_qualitative(
        moat_scores=req.moat_scores,
        risk_scores=req.risk_scores,
        moat_evidences=req.moat_evidences,
        risk_notes=req.risk_notes,
    )


# ──────────────────────────────────────────────
# E — Options
# ──────────────────────────────────────────────

@app.post("/options/sell_put")
def sell_put_endpoint(req: SellPutRequest):
    return sell_put(
        ticker=req.ticker,
        strike_price=req.strike_price,
        premium_per_share=req.premium_per_share,
        expiry=req.expiry,
        contracts=req.contracts,
        abcd_pass=req.abcd_pass,
        per_batch_budget=req.per_batch_budget,
        fair_value=req.fair_value,
        vertical_batches=req.vertical_batches,
    )


@app.post("/options/sell_call")
def sell_call_endpoint(req: SellCallRequest):
    return sell_call(
        ticker=req.ticker,
        strike_price=req.strike_price,
        premium_per_share=req.premium_per_share,
        expiry=req.expiry,
        contracts=req.contracts,
        purchase_cost_per_share=req.purchase_cost_per_share,
        shares_held=req.shares_held,
        abcd_pass=req.abcd_pass,
    )


# ──────────────────────────────────────────────
# Full Analysis (one-shot ABCDE)
# ──────────────────────────────────────────────

@app.post("/analyze")
async def analyze_endpoint(req: FullAnalysisRequest):
    try:
        financials = await fetch_financials(req.ticker)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(502, f"SEC EDGAR 抓取失敗：{e}")

    # ── 一次抓取所有 Yahoo 數據 ──────────────────────
    yahoo = fetch_yahoo_full(req.ticker)
    current_price = yahoo.get("current_price")

    # ── 自動估算（優先用使用者覆蓋值）────────────────
    roic_info = calculate_roic(financials)
    wacc_info = estimate_wacc(yahoo, financials)
    pe_info = estimate_pe_hist_avg(yahoo, financials, ticker=req.ticker)
    turnover_info = estimate_industry_asset_turnover(yahoo)
    fv_auto = estimate_fair_value(yahoo, pe_info)

    roic = req.roic if req.roic is not None else roic_info.get("roic_pct")
    wacc = req.wacc if req.wacc is not None else wacc_info.get("wacc_pct")
    industry_at = req.industry_asset_turnover_avg if req.industry_asset_turnover_avg is not None \
                  else turnover_info.get("industry_asset_turnover_avg")
    pe_hist_avg = req.pe_hist_avg if req.pe_hist_avg is not None else pe_info.get("pe_hist_avg")
    eps_ttm = yahoo.get("eps_ttm")

    # 公允價值：使用者手動輸入 > 自動分析師目標價 > PE 估算
    fair_value_used = req.fair_value_manual or fv_auto.get("auto_fair_value")
    fair_value_source = req.fair_value_source if req.fair_value_manual else fv_auto.get("primary_source", "auto")

    # ── PEACE ────────────────────────────────────────
    peace = calculate_peace(
        financials,
        industry_asset_turnover_avg=industry_at,
        roic=roic,
        wacc=wacc,
    )

    # ── Valuation ─────────────────────────────────────
    valuation = None
    if current_price:
        valuation = calculate_valuation(
            current_price=current_price,
            fair_value_manual=fair_value_used,
            fair_value_source=fair_value_source,
            eps_ttm=eps_ttm,
            pe_hist_avg=pe_hist_avg,
        )

    # ── A + B Allocation ──────────────────────────────
    horizontal = None
    vertical = None
    if req.total_investment:
        horizontal = calculate_horizontal(
            total_investment=req.total_investment,
            user_age=req.user_age,
        )
        if fair_value_used:
            per_stock = horizontal.get("per_stock_budget", 0)
            vertical = calculate_vertical(
                per_stock_budget=per_stock,
                fair_value=fair_value_used,
                current_price=current_price or 0,
                batch_count=req.batch_count,
                safety_margin_steps=req.safety_margin_steps,
            )

    # ── C Qualitative ─────────────────────────────────
    qualitative = None
    if req.moat_scores or req.risk_scores:
        qualitative = evaluate_qualitative(
            moat_scores=req.moat_scores,
            risk_scores=req.risk_scores,
            moat_evidences=req.moat_evidences,
            risk_notes=req.risk_notes,
        )

    report = generate_report(
        ticker=req.ticker,
        horizontal=horizontal,
        vertical=vertical,
        qualitative=qualitative,
        peace=peace,
        valuation=valuation,
        market_price_info=yahoo,
    )

    # ── 附加自動估算明細 ──────────────────────────────
    report["auto_estimates"] = {
        "fair_value": fv_auto,
        "roic": roic_info,
        "wacc": wacc_info,
        "pe_hist_avg": pe_info,
        "industry_asset_turnover": turnover_info,
        "data_sources": {
            "financials": "SEC EDGAR（美國官方政府財報數據庫）",
            "market_price": "Yahoo Finance（華爾街分析師共識，同 Bloomberg）",
            "analyst_targets": f"Yahoo Finance 分析師共識（{yahoo.get('analyst_count', 'N/A')} 位）",
            "sector_benchmarks": "Damodaran NYU（全球投行引用行業均值標準）",
            "wacc_methodology": "CAPM 標準公式（CFA 教科書方法論）",
        },
    }

    return report
