"""M3 QualitativeAnalyzer — 護城河 5 項 + RISK 4 項"""

MOAT_DEFINITIONS = {
    "intangible_assets": {
        "name": "無形資產",
        "description": "品牌、專利、政府特許執照",
        "key_question": "顧客是否願意付更高價格？是否能主動吸引客戶？",
        "examples": "Disney、TSMC、Pfizer、Nike",
    },
    "cost_advantage": {
        "name": "成本優勢",
        "description": "規模效應、高效率製程",
        "key_question": "能否降價並仍保持獲利？",
        "examples": "Toyota、Costco、IKEA、Samsung",
    },
    "network_effects": {
        "name": "網路效應",
        "description": "用戶數據收集與變現",
        "key_question": "用戶越多是否價值越高？",
        "examples": "Meta、Netflix、Uber、LINE",
    },
    "switching_costs": {
        "name": "高轉換成本",
        "description": "客戶難以轉換競品",
        "key_question": "客戶轉換成本是否高於企業失去客戶的代價？",
        "examples": "Adobe、Cisco、Apple iOS、Microsoft Windows",
    },
    "efficient_scale": {
        "name": "有效規模",
        "description": "利基市場近乎壟斷",
        "key_question": "新競爭者進入是否入不敷出？",
        "examples": "Boeing（duopoly）、台北捷運、台灣高鐵",
    },
}

RISK_DEFINITIONS = {
    "regulatory": {
        "code": "R",
        "name": "監管風險",
        "description": "產品/服務/行業是否高度受監管？政策是否易改變業務方向？",
        "red_flags": "能源、學貸、煙酒、特定金融服務",
    },
    "inflation": {
        "code": "I",
        "name": "通膨風險（定價能力）",
        "description": "公司是否有定價能力？漲價是否會失去客戶？",
        "red_flags": "航空公司（票價受競爭限制）、純商品型公司",
    },
    "technology": {
        "code": "S",
        "name": "科技風險",
        "description": "是否有破壞式創新可能顛覆業務？公司是否主動擁抱新技術？",
        "red_flags": "柯達案例；評估 AI / 自動化衝擊",
    },
    "key_person": {
        "code": "K",
        "name": "關鍵人物風險",
        "description": "公司運營是否高度依賴特定人物？是否有制度化 SOP？",
        "red_flags": "機師罷工 vs. 麥當勞工讀生替換難度",
    },
}


def evaluate_qualitative(
    moat_scores: dict[str, str],  # {"intangible_assets": "yes", ...}
    risk_scores: dict[str, str],  # {"regulatory": "pass", ...}
    moat_evidences: dict[str, str] | None = None,
    risk_notes: dict[str, str] | None = None,
) -> dict:
    moat_results = {}
    moat_pass_count = 0

    for key, defn in MOAT_DEFINITIONS.items():
        score = moat_scores.get(key, "unknown")
        is_hit = score in ("yes", "strong")
        if is_hit:
            moat_pass_count += 1
        moat_results[key] = {
            "name": defn["name"],
            "score": score,
            "hit": is_hit,
            "key_question": defn["key_question"],
            "evidence": (moat_evidences or {}).get(key, "未提供"),
            "confidence": "inference",
            "needs_manual_review": True,
        }

    moat_pass = moat_pass_count >= 1
    moat_verdict = (
        "strong" if moat_pass_count >= 4
        else "moderate" if moat_pass_count >= 2
        else "weak" if moat_pass_count == 1
        else "fail"
    )

    risk_results = {}
    risk_flag_count = 0

    for key, defn in RISK_DEFINITIONS.items():
        score = risk_scores.get(key, "unknown")
        is_pass = score == "pass"
        if not is_pass and score != "unknown":
            risk_flag_count += 1
        risk_results[key] = {
            "code": defn["code"],
            "name": defn["name"],
            "score": score,
            "pass": is_pass,
            "note": (risk_notes or {}).get(key, "需人工判斷"),
            "description": defn["description"],
            "confidence": "inference",
            "needs_manual_review": True,
        }

    risk_pass = risk_flag_count == 0

    return {
        "moat_analysis": {
            "results": moat_results,
            "hit_count": moat_pass_count,
            "pass": moat_pass,
            "verdict": moat_verdict,
            "threshold_note": "至少 1 項命中，越多越好",
        },
        "risk_analysis": {
            "results": risk_results,
            "flag_count": risk_flag_count,
            "pass": risk_pass,
            "threshold_note": "主觀判斷，股價波動時注意；風險不危及公司存亡即通過",
        },
        "overall_qualitative_pass": moat_pass and risk_pass,
        "global_review_required": True,
        "global_review_note": "所有質化結論均為 GPT 推估，必須人工確認後才可作為投資依據",
    }


def get_qualitative_template(ticker: str) -> dict:
    """Return the structured template for user to fill in moat and risk assessments."""
    return {
        "ticker": ticker,
        "instruction": "請對以下每個護城河填入 yes / no / partial / unknown，對 RISK 填入 pass / fail / unknown",
        "moat_template": {
            key: {
                "name": defn["name"],
                "key_question": defn["key_question"],
                "your_answer": "?",  # yes | no | partial | unknown
                "your_evidence": "",
            }
            for key, defn in MOAT_DEFINITIONS.items()
        },
        "risk_template": {
            key: {
                "code": defn["code"],
                "name": defn["name"],
                "description": defn["description"],
                "red_flags": defn["red_flags"],
                "your_verdict": "?",  # pass | fail | unknown
                "your_note": "",
            }
            for key, defn in RISK_DEFINITIONS.items()
        },
    }
