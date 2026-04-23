"""FinOps Resolver — Post-Trade Fail Desk"""

import json
import random
import re
import string
import time
from datetime import date, datetime
from html import escape as _esc

import pandas as pd
import requests
import streamlit as st


# ---------------------------------------------------------------------------
# Ollama connectivity (Phase 1)
# ---------------------------------------------------------------------------

REQUIRED_MODELS = ["finops-triage", "finops-resolver"]


def check_ollama_connection(endpoint_url):
    """Check Ollama endpoint health and model availability.

    Returns dict: reachable, models_found, models_missing, error.
    """
    url = endpoint_url.rstrip("/") + "/api/tags"
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        available = {m["name"].split(":")[0] for m in data.get("models", [])}
        found = [m for m in REQUIRED_MODELS if m in available]
        missing = [m for m in REQUIRED_MODELS if m not in available]
        return {
            "reachable": True,
            "models_found": found,
            "models_missing": missing,
            "error": None,
        }
    except requests.exceptions.Timeout:
        return {
            "reachable": False,
            "models_found": [],
            "models_missing": REQUIRED_MODELS,
            "error": f"Could not reach the AI models. Check that Ollama is running at {endpoint_url}.",
        }
    except requests.exceptions.ConnectionError:
        return {
            "reachable": False,
            "models_found": [],
            "models_missing": REQUIRED_MODELS,
            "error": f"Could not reach the AI models. Check that Ollama is running at {endpoint_url}.",
        }
    except Exception:
        return {
            "reachable": False,
            "models_found": [],
            "models_missing": REQUIRED_MODELS,
            "error": "Connection check failed. Verify the endpoint URL in the sidebar.",
        }

# ---------------------------------------------------------------------------
# Constants ported from resolver/scripts/gen_resolver.py
# ---------------------------------------------------------------------------

SETTLEMENT_TYPES = ["RVP", "DVP", "FOP"]
SETTLEMENT_DATES = ["T+0", "T+1", "T+2"]
RECALL_NOTICE_PERIOD = 3

TRIAGE_ACTIONS = ["LOCATE_AND_DELIVER", "CHASE_COUNTERPARTY", "ESCALATE_TO_MANAGER"]
LIFECYCLE_STATES = ["NEW", "OPEN", "ESCALATED", "AGED"]
DEADLINES = ["T+3", "T+5", "T+10", "T+13", "T+35"]
FLAG_POOL = [
    "THRESHOLD_SECURITY", "HIGH_VALUE", "REG_SHO_CLOSE_OUT",
    "AGED_FAIL", "LARGE_POSITION", "ILLIQUID",
]

CATEGORIES = ["CNS_FAIL", "DVP_FAIL", "B2B_PENDING", "CA_EVENT", "DK_DISPUTE"]
CATEGORY_WEIGHTS = [0.35, 0.25, 0.20, 0.12, 0.08]

CATEGORY_DISPLAY = {
    "CNS_FAIL": "CNS Fail",
    "CNS_FTD": "CNS Fail to Deliver",
    "CNS_FTR": "CNS Fail to Receive",
    "DVP_FAIL": "DVP Fail",
    "B2B_PENDING": "Broker-to-Broker Pending",
    "CA_EVENT": "Corporate Action",
    "DK_DISPUTE": "Trade Dispute (DK)",
}

TIER_DISPLAY = {
    "CRITICAL": "Critical",
    "HIGH": "High",
    "MEDIUM": "Medium",
    "LOW": "Low",
}

ESCALATION_DISPLAY = {
    "L1": "Ops Analyst",
    "L2": "Senior Ops",
    "L3": "Management",
    "L4": "Compliance",
    "NONE": "None",
}

# ---------------------------------------------------------------------------
# Firm name pools — prime brokers vs execution brokers
# ---------------------------------------------------------------------------

PRIME_BROKERS = [
    "Goldman Sachs Prime Services", "Morgan Stanley Prime Brokerage",
    "JPMorgan Prime Brokerage", "BofA Prime Brokerage",
    "Citigroup Prime Finance", "Barclays Prime Services",
    "Deutsche Bank Prime Finance", "UBS Prime Services",
    "Wells Fargo Prime Services", "Credit Suisse Prime Services",
]

EXECUTION_BROKERS = [
    "Citadel Securities", "Virtu Financial", "Jane Street",
    "Two Sigma", "Susquehanna", "Optiver", "IMC Financial Markets",
    "Flow Traders", "Wolverine Trading", "DRW Securities",
    "Knight Capital", "Instinet", "Virtu ITG",
    "Cowen Execution Services", "Canaccord Genuity",
    "Convergex", "Liquidnet", "Wedbush Securities",
    "Goldman Sachs", "Morgan Stanley", "JPMorgan",
    "Bank of America Securities", "Citigroup Global Markets",
    "Barclays Capital", "Deutsche Bank Securities",
    "UBS Securities", "Wells Fargo Securities",
    "Jefferies", "RBC Capital Markets", "TD Securities",
    "Piper Sandler", "Raymond James", "Baird",
    "Oppenheimer", "Cantor Fitzgerald", "Stifel",
    "Needham", "Cowen", "B. Riley Securities",
    "Janney Montgomery Scott", "Ladenburg Thalmann",
]

TOP_BROKER_DTCS = [
    "0005", "0050", "0062", "0089", "0161", "0164", "0188",
    "0226", "0235", "0352", "0385", "0417", "0443", "0499", "0551",
]

CUSIP_POOL = [
    "594918104",  # MSFT
    "037833100",  # AAPL
    "67066G104",  # NVDA
    "02079K107",  # GOOG
    "023135106",  # AMZN
    "30231G102",  # XOM
    "88160R101",  # TSLA
    "46625H100",  # JPM
    "78462F103",  # SPY
    "464287655",  # HD
    "571748102",  # MRK
    "500754106",  # KO
    "254709108",  # DIS
    "585055106",  # MCD
    "742718109",  # PG
    "756109104",  # RTX
    "172967424",  # CSCO
    "68389X105",  # ORCL
    "448055102",  # HUM
    "29379V103",  # EPD
    "345370860",  # F
    "895728102",  # TRV
    "624756102",  # MSCI
    "084670702",  # BRK
    "713448108",  # PEP
]


def _build_dtc_firm_map():
    """Assign execution broker names to top DTC numbers."""
    mapping = {}
    shuffled = EXECUTION_BROKERS.copy()
    random.shuffle(shuffled)
    for i, dtc in enumerate(TOP_BROKER_DTCS):
        mapping[dtc] = shuffled[i % len(shuffled)]
    return mapping


# ---------------------------------------------------------------------------
# Generation logic — ported from gen_resolver.py
# ---------------------------------------------------------------------------

def random_dtc():
    if random.random() < 0.4:
        return random.choice(TOP_BROKER_DTCS)
    return f"{random.randint(100, 9999):04d}"


def random_cusip():
    return random.choice(CUSIP_POOL)


def random_account():
    return f"ACC-{random.randint(100000, 999999)}"


def pick_ftr_count():
    """30% simple (1-3), 40% medium (5-10), 30% complex (11-28)."""
    r = random.random()
    if r < 0.3:
        return random.randint(1, 3)
    elif r < 0.7:
        return random.randint(5, 10)
    else:
        return random.randint(11, 28)


def _random_ftr_age():
    """97% bulk T+2..T+5 (normal, center T+3), 3% tail T+6..T+10."""
    if random.random() < 0.97:
        age = round(random.gauss(3, 1.0))
        return max(2, min(5, age))
    return random.randint(6, 10)


def generate_ftrs(count):
    ftrs = []
    for _ in range(count):
        ftrs.append({
            "dtc": random_dtc(),
            "age_days": _random_ftr_age(),
            "qty": random.randint(500, 25000),
            "settlement_type": random.choice(SETTLEMENT_TYPES),
            "settlement_date": random.choice(SETTLEMENT_DATES),
            "cp_fail_rate_pct": round(random.uniform(0.1, 8.0), 1),
            "partial_delivery_history": random.random() < 0.3,
        })
    ftrs.sort(key=lambda f: (-f["age_days"], -f["qty"]))
    return ftrs


def generate_triage(ftd_qty, ftrs):
    priority_score = round(random.uniform(20, 99), 1)
    if priority_score >= 80:
        tier, escalation = "CRITICAL", "L3"
    elif priority_score >= 60:
        tier, escalation = "HIGH", "L2"
    elif priority_score >= 40:
        tier, escalation = "MEDIUM", "L1"
    else:
        tier, escalation = "LOW", "L1"

    max_age = max(f["age_days"] for f in ftrs) if ftrs else 0
    flags = random.sample(FLAG_POOL, random.randint(0, 3))

    reason_parts = [f"CNS FTD {ftd_qty:,} shs"]
    if max_age > 10:
        reason_parts.append(f"aging {max_age}d")
    if "THRESHOLD_SECURITY" in flags:
        reason_parts.append("threshold security")
    if priority_score >= 80:
        reason_parts.append("high priority")

    return {
        "category": "CNS_FAIL",
        "cns_direction": "FTD",
        "lifecycle_state": random.choice(LIFECYCLE_STATES),
        "priority_score": priority_score,
        "priority_tier": tier,
        "score_components": {
            "age": round(random.uniform(0, 30), 1),
            "value": round(random.uniform(0, 30), 1),
            "regulatory": round(random.uniform(0, 20), 1),
            "counterparty": round(random.uniform(0, 20), 1),
        },
        "reason": ", ".join(reason_parts),
        "action": random.choice(TRIAGE_ACTIONS),
        "escalation_level": escalation,
        "deadline": random.choice(DEADLINES),
        "flags": flags,
    }


def generate_triage_multi_category(ftd_qty, ftrs):
    """Generate triage with varied categories, not only CNS_FAIL."""
    category = random.choices(CATEGORIES, weights=CATEGORY_WEIGHTS, k=1)[0]

    priority_score = round(random.uniform(20, 99), 1)

    if category == "CNS_FAIL":
        cns_direction = random.choice(["FTD", "FTR"])
        if priority_score < 26:
            priority_score = round(random.uniform(26, 50), 1)
    else:
        cns_direction = "N_A"

    if priority_score >= 76:
        tier, escalation = "CRITICAL", "L3"
    elif priority_score >= 51:
        tier, escalation = "HIGH", "L2"
    elif priority_score >= 26:
        tier, escalation = "MEDIUM", "L1"
    else:
        tier, escalation = "LOW", "NONE"

    max_age = max(f["age_days"] for f in ftrs) if ftrs else 0
    flags = random.sample(FLAG_POOL, random.randint(0, 3))

    reason_parts = [f"{CATEGORY_DISPLAY[category]} — {ftd_qty:,} shs"]
    if max_age > 5:
        reason_parts.append(f"aging {max_age}d")
    if "THRESHOLD_SECURITY" in flags:
        reason_parts.append("threshold security")
    if priority_score >= 76:
        reason_parts.append("high priority")

    return {
        "category": category,
        "cns_direction": cns_direction,
        "lifecycle_state": random.choice(LIFECYCLE_STATES),
        "priority_score": priority_score,
        "priority_tier": tier,
        "score_components": {
            "age": round(random.uniform(0, 30), 1),
            "value": round(random.uniform(0, 30), 1),
            "regulatory": round(random.uniform(0, 20), 1),
            "counterparty": round(random.uniform(0, 20), 1),
        },
        "reason": ", ".join(reason_parts),
        "action": random.choice(TRIAGE_ACTIONS),
        "escalation_level": escalation,
        "deadline": random.choice(DEADLINES),
        "flags": flags,
    }


def generate_inventory():
    return {
        "box_qty": random.randint(500, 20000) if random.random() < 0.70 else 0,
        "stock_loan_available": random.randint(500, 25000) if random.random() < 0.60 else 0,
        "recall_outstanding": random.randint(500, 30000) if random.random() < 0.65 else 0,
        "pending_receives": random.randint(0, 5000),
    }


def select_fallbacks(inventory, remaining, deadline_days):
    recall = inventory["recall_outstanding"]
    borrow = inventory["stock_loan_available"]
    box = inventory["box_qty"]

    tight_deadline = deadline_days <= RECALL_NOTICE_PERIOD
    if tight_deadline and recall > 0 and borrow > 0 and remaining > recall:
        rqty = min(recall, remaining)
        bqty = min(borrow, remaining - rqty)
        return "INITIATE_RECALL", rqty, "SOURCE_BORROW", bqty, True

    if recall > 0:
        prim, pqty = "INITIATE_RECALL", min(recall, remaining)
        rem = remaining - pqty
        if borrow > 0 and rem > 0:
            return prim, pqty, "SOURCE_BORROW", min(borrow, rem), False
        if box > 0 and rem > 0:
            return prim, pqty, "APPLY_BOX", min(box, rem), False
        return prim, pqty, "BUY_IN_NOTICE", 0, False

    if box > 0:
        prim, pqty = "APPLY_BOX", min(box, remaining)
        rem = remaining - pqty
        if borrow > 0 and rem > 0:
            return prim, pqty, "SOURCE_BORROW", min(borrow, rem), False
        return prim, pqty, "BUY_IN_NOTICE", 0, False

    if borrow > 0:
        return "SOURCE_BORROW", min(borrow, remaining), "BUY_IN_NOTICE", 0, False

    return "BUY_IN_NOTICE", 0, "BUY_IN_NOTICE", 0, False


def generate_related_fails(ftrs):
    unique_cps = len({f["dtc"] for f in ftrs})
    aged = sum(1 for f in ftrs if f["age_days"] >= 5)
    has_gridlock = unique_cps >= 3 and (
        any(f["age_days"] >= 7 for f in ftrs) or aged >= 2
    )

    fails = []
    if has_gridlock:
        parties = sorted({f["dtc"] for f in ftrs})
        for party in parties[: random.randint(1, min(3, len(parties)))]:
            fails.append({
                "category": random.choice(["DVP_FAIL", "CNS_FAIL"]),
                "dtc": party,
                "qty": random.randint(1000, 30000),
                "side": random.choice(["Buy", "Sell"]),
                "age_days": random.randint(2, 15),
            })
    elif random.random() < 0.3:
        for _ in range(random.randint(1, 2)):
            fails.append({
                "category": random.choice(["DVP_FAIL", "CNS_FAIL"]),
                "dtc": random_dtc(),
                "qty": random.randint(500, 10000),
                "side": random.choice(["Buy", "Sell"]),
                "age_days": random.randint(1, 5),
            })
    return fails


def _market_value():
    """Generate a realistic market value across tiers."""
    r = random.random()
    if r < 0.20:
        return round(random.uniform(10_000, 99_999), 2)
    elif r < 0.45:
        return round(random.uniform(100_000, 499_999), 2)
    elif r < 0.65:
        return round(random.uniform(500_000, 999_999), 2)
    elif r < 0.85:
        return round(random.uniform(1_000_000, 5_000_000), 2)
    else:
        return round(random.uniform(5_000_000, 25_000_000), 2)


def _format_market_value(val):
    if val >= 1_000_000:
        return f"${val / 1_000_000:.1f}M"
    elif val >= 1_000:
        return f"${val / 1_000:.0f}K"
    else:
        return f"${val:,.0f}"


def _pick_firm(category, dtc, dtc_firm_map, stock_loan_context=False):
    """Pick firm name based on category and context."""
    if stock_loan_context:
        return random.choice(PRIME_BROKERS)
    if dtc in dtc_firm_map:
        return dtc_firm_map[dtc]
    firm_name = random.choice(EXECUTION_BROKERS)
    dtc_firm_map[dtc] = firm_name
    return firm_name


def generate_fail(dtc_firm_map):
    """Generate a single fail scenario with all data needed for display and pipeline."""
    ftr_count = pick_ftr_count()
    ftrs = generate_ftrs(ftr_count)
    ftr_total = sum(f["qty"] for f in ftrs)
    ftd_qty = ftr_total + random.randint(1000, 50000)

    cusip = random_cusip()
    cp_dtc = random_dtc()
    account = random_account()
    market_value = _market_value()
    age_days = random.randint(1, 20)
    side = random.choice(["Sell", "Buy"])
    inv_coverage = random.randint(0, 175)
    cp_fail_rate = round(random.uniform(0.1, 9.5), 1)
    reg_sho = random.random() < 0.3

    triage = generate_triage_multi_category(ftd_qty, ftrs)
    category = triage["category"]
    cns_direction = triage.get("cns_direction", "N_A")

    if category == "CNS_FAIL":
        firm_name = "CNS"
    else:
        firm_name = _pick_firm(category, cp_dtc, dtc_firm_map)

    if category == "CNS_FAIL" and cns_direction == "FTR":
        side = "Buy"
        ftd_qty, ftr_total = ftr_total, ftd_qty
    inventory = generate_inventory()

    for ftr in ftrs:
        if ftr["dtc"] not in dtc_firm_map:
            dtc_firm_map[ftr["dtc"]] = random.choice(EXECUTION_BROKERS)

    related_fails = generate_related_fails(ftrs)
    for rf in related_fails:
        if rf["dtc"] not in dtc_firm_map:
            dtc_firm_map[rf["dtc"]] = random.choice(EXECUTION_BROKERS)

    tier = triage["priority_tier"]
    esc = triage["escalation_level"]
    if tier == "CRITICAL":
        escalation_risk = "High"
    elif tier == "HIGH" or esc in ("L2", "L3", "L4"):
        escalation_risk = "Moderate"
    else:
        escalation_risk = "Low"

    return {
        "cusip": cusip,
        "firm_name": firm_name,
        "dtc": f"DTC-{cp_dtc}",
        "account": account,
        "category": f"CNS_{cns_direction}" if category == "CNS_FAIL" else triage["category"],
        "cns_direction": cns_direction,
        "side": side,
        "ftd_qty": ftd_qty,
        "market_value": market_value,
        "age_days": age_days,
        "priority_score": triage["priority_score"],
        "priority_tier": triage["priority_tier"],
        "escalation_level": triage["escalation_level"],
        "escalation_risk": escalation_risk,
        "lifecycle_state": triage["lifecycle_state"],
        "reg_sho": reg_sho,
        "inv_coverage_pct": inv_coverage,
        "cp_fail_rate_pct": cp_fail_rate,
        "flags": triage["flags"],
        "triage": triage,
        "inventory": inventory,
        "ftrs": ftrs,
        "ftr_count": ftr_count,
        "related_fails": related_fails,
    }


def generate_fails(count):
    dtc_firm_map = _build_dtc_firm_map()
    fails = [generate_fail(dtc_firm_map) for _ in range(count)]
    return fails, dtc_firm_map


# ---------------------------------------------------------------------------
# Stage 1 — Triage pipeline (Phase 2)
# ---------------------------------------------------------------------------

TRIAGE_SYSTEM_PROMPT = (
    "You are a post-trade settlement triage assistant. Given a fail record, "
    "calculate the priority score using the weighted formula (Age 30%, Value 25%, "
    "Regulatory 35%, CP History 10%, with Inventory and Concentration modifiers), "
    "apply category priority hierarchy overrides, classify the fail including CNS "
    "direction (FTD/FTR), and output a JSON object conforming exactly to the "
    "required schema. Output JSON only — no explanation, no markdown, no preamble."
)

FLAG_DISPLAY = {
    "THRESHOLD_SECURITY": "Regulatory Watchlist Security",
    "HIGH_VALUE": "High Value Position",
    "REG_SHO_CLOSE_OUT": "Reg SHO Close-Out Risk",
    "REG_SHO_CLOSEOUT": "Reg SHO Close-Out Risk",
    "AGED_FAIL": "Aged Fail",
    "LARGE_POSITION": "Large Position",
    "ILLIQUID": "Illiquid Security",
    "CONCENTRATION_RISK": "Concentration Risk",
    "PROBLEM_CP": "Problem Counterparty",
}

ESCALATION_DISPLAY_FULL = {
    "L1": "Operations Analyst Review",
    "L2": "Senior Ops Review",
    "L3": "Management Escalation",
    "L4": "Compliance Escalation",
    "NONE": "None",
}


def format_triage_prompt(fail):
    """Build the pipe-delimited prompt matching triage training data format."""
    mv = fail["market_value"]
    if mv >= 1_000_000:
        mv_str = f"${mv / 1_000_000:.1f}M"
    else:
        mv_str = f"${mv:,.0f}"

    parts = [
        f"CUSIP: {fail['cusip']}",
        f"Side: {fail['side']}",
        f"Qty: {fail['ftd_qty']}",
        f"Counterparty: {fail['dtc']}",
        f"Age: {fail['age_days']} {'day' if fail['age_days'] == 1 else 'days'}",
        f"Market Value: {mv_str}",
    ]

    category = fail["category"]
    cns_dir = fail["triage"]["cns_direction"]

    if category.startswith("CNS_"):
        sign = "-" if cns_dir == "FTD" else "+"
        parts.append(f"CNS Position: {sign}{fail['ftd_qty']}")
        parts.append(f"CNS Direction: {cns_dir}")
    elif category == "DVP_FAIL":
        parts.append("Settlement Type: DVP")
    elif category == "B2B_PENDING":
        parts.append("Street-Side Status: Pending")
    elif category == "CA_EVENT":
        ca_types = ["Dividend", "Stock Split", "Merger", "Spin-Off"]
        parts.append(f"CA Type: {random.choice(ca_types)}")
    elif category == "DK_DISPUTE":
        reasons = ["Unmatched", "Price Dispute", "Quantity Dispute"]
        parts.append(f"Dispute Reason: {random.choice(reasons)}")

    parts.append(f"Reg SHO Threshold: {'Yes' if fail['reg_sho'] else 'No'}")
    parts.append(f"Inventory Coverage: {fail['inv_coverage_pct']}%")
    parts.append(f"CP 15-day Fail Rate: {fail['cp_fail_rate_pct']}%")

    return "Triage this fail record:\n" + " | ".join(parts)


def call_triage(endpoint_url, fail):
    """Call finops-triage via Ollama /api/chat and return parsed JSON."""
    url = endpoint_url.rstrip("/") + "/api/chat"
    prompt = format_triage_prompt(fail)
    payload = {
        "model": "finops-triage",
        "messages": [
            {"role": "system", "content": TRIAGE_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }
    try:
        resp = requests.post(url, json=payload, timeout=120)
        resp.raise_for_status()
        content = resp.json()["message"]["content"]
        return {"ok": True, "data": json.loads(content), "raw_prompt": prompt, "raw_content": content}
    except requests.exceptions.Timeout:
        return {"ok": False, "error": "Stage 1 triage timed out. Try again or check the Ollama endpoint."}
    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": "Stage 1 triage timed out. Try again or check the Ollama endpoint."}
    except (json.JSONDecodeError, KeyError, ValueError):
        return {"ok": False, "error": "Stage 1 returned an unexpected response. Try again."}
    except Exception:
        return {"ok": False, "error": "Stage 1 returned an unexpected response. Try again."}


def _is_connected():
    """Check if connection state is confirmed green."""
    conn = st.session_state.get("conn")
    return conn is not None and conn["reachable"] and not conn["models_missing"]


# ---------------------------------------------------------------------------
# Stage 2 — Resolver pipeline (Phase 3)
# ---------------------------------------------------------------------------

RESOLVER_SYSTEM_PROMPT = (
    "You are a post-trade settlement resolution assistant. Given a triage output, "
    "inventory snapshot, and pending FTRs for a CUSIP, recommend an ordered resolution "
    "sequence following the KB resolution logic. Chase FTRs first (oldest then largest), "
    "apply free box, recall before borrow. Apply partials immediately. Detect and flag "
    "gridlock. Output JSON only — no explanation, no markdown, no preamble."
)

ACTION_DISPLAY = {
    "CHASE_FTR": "Contact counterparty to deliver shares",
    "APPLY_BOX": "Apply available inventory",
    "INITIATE_RECALL": "Recall shares from lending program",
    "SOURCE_BORROW": "Source external stock loan",
    "PARTIAL_DELIVER": "Deliver available shares immediately",
    "DEPOT_MOVEMENT": "Transfer shares to depository",
    "NET_GRIDLOCK": "Propose coordinated net settlement",
    "BUY_IN_NOTICE": "Issue formal buy-in notice",
    "SPO_SETTLEMENT": "Cash settle via Special Payment Order",
    "OFFSET_FTR": "Apply pending receipt against obligation",
    "ESCALATE": "Escalate for manual resolution",
}

FALLBACK_DISPLAY = {
    "INITIATE_RECALL": "recall shares from lending",
    "SOURCE_BORROW": "source external stock loan",
    "APPLY_BOX": "apply available inventory",
    "NET_GRIDLOCK": "propose coordinated net settlement",
    "BUY_IN_NOTICE": "issue formal buy-in notice",
    "SPO_SETTLEMENT": "cash settle via Special Payment Order",
    "ESCALATE": "escalate for manual resolution",
    "STOCK_LOAN": "source external stock loan",
    "RECALL": "recall shares from lending",
}


def parse_think_response(text):
    match = re.search(r"<think>(.*?)</think>(.*)", text, flags=re.DOTALL)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    return None, text.strip()


def _dtc_to_firm(dtc_code, dtc_firm_map):
    raw = dtc_code.replace("DTC-", "")
    return dtc_firm_map.get(raw, dtc_code)


def compose_resolver_input(fail, triage_data):
    ftrs_formatted = []
    for ftr in fail["ftrs"]:
        ftr_copy = dict(ftr)
        if not str(ftr_copy["dtc"]).startswith("DTC-"):
            ftr_copy["dtc"] = f"DTC-{ftr_copy['dtc']}"
        ftrs_formatted.append(ftr_copy)

    related_formatted = []
    for rf in fail.get("related_fails", []):
        rf_copy = dict(rf)
        if not str(rf_copy["dtc"]).startswith("DTC-"):
            rf_copy["dtc"] = f"DTC-{rf_copy['dtc']}"
        related_formatted.append(rf_copy)

    return {
        "triage": triage_data,
        "cusip": fail["cusip"],
        "ftd_qty": fail["ftd_qty"],
        "inventory": fail["inventory"],
        "ftrs": ftrs_formatted,
        "related_fails": related_formatted,
    }


def call_resolver(endpoint_url, fail, triage_data):
    url = endpoint_url.rstrip("/") + "/api/chat"
    resolver_input = compose_resolver_input(fail, triage_data)
    prompt = "Resolve this fail:\n" + json.dumps(resolver_input)

    payload = {
        "model": "finops-resolver",
        "messages": [
            {"role": "system", "content": RESOLVER_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
    }

    try:
        resp = requests.post(url, json=payload, timeout=180)
        resp.raise_for_status()
        content = resp.json()["message"]["content"]
        thinking, json_text = parse_think_response(content)
        return {
            "ok": True,
            "data": json.loads(json_text),
            "thinking": thinking,
            "raw_prompt": prompt,
            "raw_content": content,
        }
    except requests.exceptions.Timeout:
        return {
            "ok": False,
            "error": "Stage 2 resolution timed out. Complex scenarios may take up to 30 seconds.",
        }
    except requests.exceptions.ConnectionError:
        return {
            "ok": False,
            "error": "Stage 2 could not reach the AI models. Check Ollama endpoint.",
        }
    except (json.JSONDecodeError, KeyError, ValueError):
        return {
            "ok": False,
            "error": "Stage 2 returned an unexpected response. Try again.",
        }
    except Exception:
        return {
            "ok": False,
            "error": "Stage 2 returned an unexpected response. Try again.",
        }


# ---------------------------------------------------------------------------
# Display support — CUSIP info, helpers
# ---------------------------------------------------------------------------

CUSIP_INFO = {
    "594918104": ("MSFT", "Microsoft"),
    "037833100": ("AAPL", "Apple Inc."),
    "67066G104": ("NVDA", "NVIDIA"),
    "02079K107": ("GOOGL", "Alphabet"),
    "023135106": ("AMZN", "Amazon"),
    "30231G102": ("XOM", "ExxonMobil"),
    "88160R101": ("TSLA", "Tesla"),
    "46625H100": ("JPM", "JPMorgan Chase"),
    "78462F103": ("SPY", "SPDR S&P 500"),
    "464287655": ("HD", "Home Depot"),
    "571748102": ("MRK", "Merck & Co."),
    "500754106": ("KO", "Coca-Cola"),
    "254709108": ("DIS", "Walt Disney"),
    "585055106": ("MCD", "McDonald's"),
    "742718109": ("PG", "Procter & Gamble"),
    "756109104": ("RTX", "RTX Corp"),
    "172967424": ("CSCO", "Cisco Systems"),
    "68389X105": ("ORCL", "Oracle Corp"),
    "448055102": ("HUM", "Humana"),
    "29379V103": ("EPD", "Enterprise Products"),
    "345370860": ("F", "Ford Motor"),
    "895728102": ("TRV", "Travelers"),
    "624756102": ("MSCI", "MSCI Inc."),
    "084670702": ("BRK.B", "Berkshire Hathaway"),
    "713448108": ("PEP", "PepsiCo"),
}


def _ticker(cusip):
    return CUSIP_INFO.get(cusip, (cusip[:6], cusip))[0]


def _ticker_name(cusip):
    return CUSIP_INFO.get(cusip, (cusip[:6], cusip))[1]


def _is_prime(firm):
    return firm in PRIME_BROKERS


def _has_gridlock(fail):
    return len(fail.get("related_fails", [])) > 0


def _reg_sho_days(fail):
    return max(1, 13 - fail["age_days"]) if fail["reg_sho"] else None


def _fmt_mv(val):
    if val >= 1_000_000:
        return f"${val / 1_000_000:.2f}M"
    if val >= 1_000:
        return f"${val / 1_000:.0f}K"
    return f"${val:,.0f}"


def _age_cls(age):
    if age >= 10:
        return "age-crit"
    if age >= 7:
        return "age-warn"
    if age >= 4:
        return "age-ok"
    return "age-fresh"


def _pri_cls(score):
    if score >= 76:
        return "crit"
    if score >= 51:
        return "warn"
    if score >= 26:
        return "ok"
    return ""


def _sort_fails(fails):
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    return sorted(
        fails,
        key=lambda f: (order.get(f["priority_tier"], 4), -f["age_days"], -f["priority_score"]),
    )


def _apply_filter(fails, filt):
    if filt == "ALL":
        return fails
    if filt == "REG SHO":
        return [f for f in fails if f["reg_sho"]]
    if filt == "GRIDLOCK":
        return [f for f in fails if _has_gridlock(f)]
    return [f for f in fails if f["priority_tier"] == filt]


# ---------------------------------------------------------------------------
# CSS Theme — ported from FinOps Resolver HTML design
# ---------------------------------------------------------------------------

THEME_CSS = """<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
    --fo-bg: #0a0b0d;
    --fo-panel: #101217;
    --fo-panel-2: #151823;
    --fo-panel-3: #1b1f2a;
    --fo-hair: #20242f;
    --fo-hair-2: #2a2f3d;
    --fo-text: #d7dae1;
    --fo-text-dim: #8a8f9c;
    --fo-text-mute: #5a5f6c;
    --fo-accent: #4ED6C9;
    --fo-accent-ink: #0a0b0d;
    --fo-crit: #ff5a5f;
    --fo-crit-bg: rgba(255,90,95,0.10);
    --fo-warn: #ffb547;
    --fo-warn-bg: rgba(255,181,71,0.10);
    --fo-ok: #52d18a;
    --fo-ok-bg: rgba(82,209,138,0.10);
    --fo-fresh: #2f8a5a;
    --fo-fresh-bg: rgba(47,138,90,0.12);
    --fo-mono: "JetBrains Mono", "IBM Plex Mono", ui-monospace, monospace;
    --fo-sans: "Inter", ui-sans-serif, system-ui, sans-serif;
}

/* === Streamlit overrides === */
.stApp { background: var(--fo-bg) !important; }
header[data-testid="stHeader"] { display: none !important; }
footer { display: none !important; }
.stDeployButton { display: none !important; }
.block-container {
    padding-top: 0 !important;
    padding-bottom: 0 !important;
    max-width: 100% !important;
    padding-left: 0.5rem !important;
    padding-right: 0.5rem !important;
}
section[data-testid="stSidebar"] { display: none !important; }
[data-testid="stHorizontalBlock"] { gap: 0 !important; }
hr { border-color: var(--fo-hair) !important; opacity: 1 !important; }

/* Column border */
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child {
    border-right: 1px solid var(--fo-hair);
    padding-right: 0 !important;
}
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:last-child {
    padding-left: 0 !important;
}

/* Selectbox */
.stSelectbox label { display: none !important; }
.stSelectbox [data-baseweb="select"] {
    font-family: var(--fo-mono) !important;
    font-size: 11px !important;
}

/* Radio buttons */
.stRadio > div { flex-wrap: wrap !important; }
.stRadio label span {
    font-family: var(--fo-mono) !important;
    font-size: 10px !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
}

/* Buttons */
.stButton > button {
    font-family: var(--fo-mono) !important;
    font-size: 10.5px !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    border-radius: 3px !important;
}

/* Expander */
[data-testid="stExpander"] {
    background: var(--fo-panel-2) !important;
    border: 1px solid var(--fo-hair) !important;
    border-radius: 0 !important;
}
[data-testid="stExpander"] summary span {
    font-family: var(--fo-mono) !important;
    font-size: 10px !important;
    letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    color: var(--fo-text-dim) !important;
}

/* === Top bar === */
.fo-topbar {
    display: flex; align-items: center;
    background: var(--fo-panel);
    border-bottom: 1px solid var(--fo-hair);
    padding: 10px 14px; gap: 14px;
}
.fo-brand { display: flex; align-items: center; gap: 10px; }
.fo-brand-mark {
    width: 22px; height: 22px; border-radius: 3px;
    background: var(--fo-accent); color: var(--fo-accent-ink);
    display: grid; place-items: center;
    font-family: var(--fo-mono); font-weight: 700; font-size: 13px;
}
.fo-brand-name { font-family: var(--fo-mono); font-weight: 600; font-size: 12px; letter-spacing: 0.08em; color: var(--fo-text); }
.fo-brand-sub { font-family: var(--fo-mono); font-size: 10px; letter-spacing: 0.06em; color: var(--fo-text-dim); }
.fo-top-right { margin-left: auto; display: flex; align-items: center; gap: 14px; }
.fo-status-cluster { display: flex; gap: 16px; font-family: var(--fo-mono); font-size: 10px; color: var(--fo-text-dim); }
.fo-status-item { display: flex; align-items: center; gap: 6px; }
.fo-label { color: var(--fo-text-mute); letter-spacing: 0.1em; text-transform: uppercase; }
.fo-val { color: var(--fo-text); }
.fo-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }
.fo-dot.ok { background: var(--fo-ok); box-shadow: 0 0 6px var(--fo-ok); }
.fo-dot.warn { background: var(--fo-warn); box-shadow: 0 0 6px var(--fo-warn); }

/* === KPI strip === */
.fo-kpis {
    display: grid; grid-template-columns: repeat(7, 1fr);
    background: var(--fo-panel);
    border-bottom: 1px solid var(--fo-hair);
}
.fo-kpi {
    padding: 10px 14px; border-right: 1px solid var(--fo-hair);
    display: flex; flex-direction: column; gap: 4px;
}
.fo-kpi:last-child { border-right: 0; }
.fo-kpi-label { font-family: var(--fo-mono); font-size: 9.5px; letter-spacing: 0.12em; text-transform: uppercase; color: var(--fo-text-dim); }
.fo-kpi-val { font-family: var(--fo-mono); font-size: 22px; font-weight: 500; color: var(--fo-text); line-height: 1; }
.fo-kpi-val.crit { color: var(--fo-crit); }
.fo-kpi-val.warn { color: var(--fo-warn); }
.fo-kpi-val.ok { color: var(--fo-ok); }
.fo-kpi-sub { font-family: var(--fo-mono); font-size: 9.5px; color: var(--fo-text-mute); }

/* === Queue table === */
.fo-queue-head {
    display: flex; align-items: center; gap: 10px;
    padding: 8px 12px; background: var(--fo-panel);
    border-bottom: 1px solid var(--fo-hair);
}
.fo-panel-title { font-family: var(--fo-mono); font-size: 11px; letter-spacing: 0.12em; text-transform: uppercase; color: var(--fo-text); }
.fo-panel-sub { font-family: var(--fo-mono); font-size: 10px; color: var(--fo-text-dim); margin-left: 8px; }
.fo-queue-scroll { overflow: auto; max-height: calc(100vh - 320px); min-height: 300px; }

table.fo-qtab {
    width: 100%; border-collapse: separate; border-spacing: 0;
    font-family: var(--fo-mono); font-size: 11px;
}
table.fo-qtab thead th {
    position: sticky; top: 0; z-index: 2;
    background: var(--fo-panel); color: var(--fo-text-dim);
    font-weight: 500; text-transform: uppercase; letter-spacing: 0.08em;
    font-size: 9.5px; padding: 7px 8px; text-align: left;
    border-bottom: 1px solid var(--fo-hair-2); white-space: nowrap;
}
table.fo-qtab thead th.r { text-align: right; }
table.fo-qtab tbody td {
    padding: 6px 8px; border-bottom: 1px solid var(--fo-hair);
    white-space: nowrap; vertical-align: middle; color: var(--fo-text);
}
table.fo-qtab tbody td.r { text-align: right; }
table.fo-qtab tbody tr.is-sel {
    background: rgba(78,214,201,0.06);
    box-shadow: inset 3px 0 0 var(--fo-accent);
}

.fo-tdot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }
.fo-tdot.tier-critical { background: var(--fo-crit); box-shadow: 0 0 5px var(--fo-crit); }
.fo-tdot.tier-high { background: var(--fo-warn); }
.fo-tdot.tier-medium { background: var(--fo-ok); }
.fo-tdot.tier-low { background: var(--fo-fresh); }
.fo-tn { font-size: 10px; letter-spacing: 0.08em; }
.fo-tn.tier-critical { color: var(--fo-crit); }
.fo-tn.tier-high { color: var(--fo-warn); }
.fo-tn.tier-medium { color: var(--fo-ok); }
.fo-tn.tier-low { color: var(--fo-fresh); }

.fo-age-pill { display: inline-block; min-width: 30px; padding: 2px 6px; text-align: center; border-radius: 2px; font-size: 10.5px; }
.fo-age-pill.age-crit { background: var(--fo-crit-bg); color: var(--fo-crit); }
.fo-age-pill.age-warn { background: var(--fo-warn-bg); color: var(--fo-warn); }
.fo-age-pill.age-ok { background: var(--fo-ok-bg); color: var(--fo-ok); }
.fo-age-pill.age-fresh { background: var(--fo-fresh-bg); color: var(--fo-fresh); }

.fo-rs-pill { background: var(--fo-crit-bg); color: var(--fo-crit); padding: 1px 5px; border-radius: 2px; font-size: 10px; }
.fo-cov-wrap { display: inline-flex; align-items: center; gap: 6px; }
.fo-spark { background: var(--fo-panel-3); border-radius: 1px; overflow: hidden; display: inline-block; }
.fo-spark-fill { height: 100%; display: block; }
.fo-cov-n { color: var(--fo-text-dim); font-size: 10px; }
.fo-cp-dot { display: inline-block; width: 5px; height: 5px; border-radius: 50%; margin-right: 5px; vertical-align: middle; }
.fo-cp-dot.prime { background: var(--fo-accent); }
.fo-cp-dot.exec { background: var(--fo-text-mute); }
.fo-fchips { display: inline-flex; gap: 4px; }
.fo-fchip { font-size: 9px; letter-spacing: 0.04em; padding: 1px 5px; border: 1px solid var(--fo-hair-2); color: var(--fo-text-dim); border-radius: 2px; }
.fo-fchip-more { font-size: 9px; color: var(--fo-text-mute); padding: 1px 3px; }
.fo-ai-done { color: var(--fo-accent); }
.fo-ai-pending { color: var(--fo-text-mute); }
.fo-sym { color: var(--fo-text); }
.fo-cusip { color: var(--fo-text-mute); font-size: 9.5px; }

/* === Detail panel === */
.fo-detail-head {
    padding: 12px 16px; background: var(--fo-panel);
    border-bottom: 1px solid var(--fo-hair);
}
.fo-fid-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 6px; }
.fo-fid-label { font-family: var(--fo-mono); font-size: 9.5px; letter-spacing: 0.12em; color: var(--fo-text-mute); }
.fo-fid-value { font-family: var(--fo-mono); font-size: 12px; color: var(--fo-text); }
.fo-chip {
    font-family: var(--fo-mono); font-size: 9.5px; letter-spacing: 0.1em;
    padding: 2px 7px; border-radius: 2px; text-transform: uppercase;
    display: inline-block;
}
.fo-chip.tier-critical { background: var(--fo-crit-bg); color: var(--fo-crit); }
.fo-chip.tier-high { background: var(--fo-warn-bg); color: var(--fo-warn); }
.fo-chip.tier-medium { background: var(--fo-ok-bg); color: var(--fo-ok); }
.fo-chip.tier-low { background: var(--fo-fresh-bg); color: var(--fo-fresh); }
.fo-chip-regsho { background: var(--fo-crit-bg); color: var(--fo-crit); }
.fo-chip-gridlock { background: var(--fo-warn-bg); color: var(--fo-warn); }

.fo-fail-title { font-family: var(--fo-mono); font-size: 18px; font-weight: 500; color: var(--fo-text); margin: 0 0 4px; }
.fo-fail-sub { font-family: var(--fo-mono); font-size: 10.5px; color: var(--fo-text-dim); letter-spacing: 0.04em; }

/* === Metric strip === */
.fo-mstrip {
    display: grid; grid-template-columns: repeat(6, 1fr);
    background: var(--fo-panel); border-bottom: 1px solid var(--fo-hair);
}
.fo-ms { padding: 10px 12px; border-right: 1px solid var(--fo-hair); display: flex; flex-direction: column; gap: 3px; }
.fo-ms:last-child { border-right: 0; }
.fo-ms-l { font-family: var(--fo-mono); font-size: 9px; letter-spacing: 0.14em; color: var(--fo-text-dim); text-transform: uppercase; }
.fo-ms-v { font-family: var(--fo-mono); font-size: 20px; font-weight: 500; color: var(--fo-text); line-height: 1; }
.fo-ms-v.crit { color: var(--fo-crit); }
.fo-ms-v.warn { color: var(--fo-warn); }
.fo-ms-v.ok { color: var(--fo-ok); }
.fo-ms-v .sm { font-size: 12px; color: var(--fo-text-dim); font-weight: 400; }
.fo-ms-s { font-family: var(--fo-mono); font-size: 9.5px; color: var(--fo-text-mute); }
.fo-cov-bar { height: 4px; width: 100%; background: var(--fo-panel-3); border-radius: 2px; margin-top: 4px; overflow: hidden; }
.fo-cov-bar-fill { height: 100%; }
.fo-flag-wrap { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 2px; }
.fo-flag-tag {
    padding: 2px 7px; background: var(--fo-panel-3);
    border: 1px solid var(--fo-hair-2); border-radius: 2px;
    font-family: var(--fo-mono); font-size: 9.5px; color: var(--fo-text-dim);
}

/* === Stage cards === */
.fo-stage-card { padding: 14px 18px 22px; }
.fo-stage-head {
    display: flex; align-items: center; gap: 10px;
    margin-bottom: 12px; padding-bottom: 10px;
    border-bottom: 1px solid var(--fo-hair);
}
.fo-stage-num {
    width: 28px; height: 28px; border-radius: 3px;
    background: var(--fo-panel-3); color: var(--fo-accent);
    font-family: var(--fo-mono); font-weight: 600; font-size: 12px;
    display: grid; place-items: center;
}
.fo-stage-title { font-family: var(--fo-mono); font-size: 11px; letter-spacing: 0.1em; text-transform: uppercase; color: var(--fo-text); }
.fo-stage-sub { font-family: var(--fo-mono); font-size: 9.5px; color: var(--fo-text-dim); }
.fo-assessment { font-family: var(--fo-sans); font-size: 13px; line-height: 1.7; color: var(--fo-text); margin-bottom: 14px; }
.fo-kv-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 20px; margin-top: 6px; }
.fo-kv { display: flex; justify-content: space-between; gap: 8px; padding: 6px 0; border-bottom: 1px dashed var(--fo-hair); }
.fo-kv .k { font-family: var(--fo-mono); font-size: 9.5px; color: var(--fo-text-dim); letter-spacing: 0.08em; text-transform: uppercase; }
.fo-kv .v { font-family: var(--fo-mono); font-size: 11px; color: var(--fo-text); }

/* Banners */
.fo-banner {
    padding: 9px 12px; border-radius: 3px;
    font-family: var(--fo-mono); font-size: 10.5px;
    margin-bottom: 12px; letter-spacing: 0.02em; border-left: 3px solid;
}
.fo-banner.crit { background: var(--fo-crit-bg); color: var(--fo-crit); border-color: var(--fo-crit); }
.fo-banner.warn { background: var(--fo-warn-bg); color: var(--fo-warn); border-color: var(--fo-warn); }
.fo-banner.ok { background: var(--fo-ok-bg); color: var(--fo-ok); border-color: var(--fo-ok); }

/* Steps */
.fo-steps-title { font-family: var(--fo-mono); font-size: 10px; letter-spacing: 0.12em; color: var(--fo-text-dim); text-transform: uppercase; margin-bottom: 8px; }
.fo-steps { list-style: none; padding: 0; margin: 0 0 16px; }
.fo-steps li { display: flex; gap: 12px; padding: 8px 0; border-bottom: 1px solid var(--fo-hair); align-items: flex-start; }
.fo-steps li:last-child { border-bottom: 0; }
.fo-step-n { color: var(--fo-accent); font-size: 11px; min-width: 24px; font-family: var(--fo-mono); }
.fo-step-t { font-family: var(--fo-sans); font-size: 12.5px; line-height: 1.6; color: var(--fo-text); }

.fo-subhead { font-family: var(--fo-mono); font-size: 10px; letter-spacing: 0.12em; color: var(--fo-text-dim); text-transform: uppercase; margin: 14px 0 6px; }
.fo-prose { font-family: var(--fo-sans); font-size: 12.5px; line-height: 1.65; color: var(--fo-text); }

/* Trace */
.fo-trace-body { font-family: var(--fo-mono); font-size: 10.5px; color: var(--fo-text-dim); line-height: 1.7; }
.fo-trace-line { display: flex; gap: 10px; padding: 3px 0; }
.fo-trace-n { color: var(--fo-accent); min-width: 22px; }
.fo-trace-t { color: var(--fo-text-dim); }

/* Status bar */
.fo-statusbar {
    background: var(--fo-panel); border-top: 1px solid var(--fo-hair);
    display: flex; align-items: center; padding: 4px 14px; gap: 8px;
    font-family: var(--fo-mono); font-size: 10px; color: var(--fo-text-mute);
    letter-spacing: 0.06em; margin-top: 4px;
}
.fo-statusbar .v { color: var(--fo-text-dim); }

/* Empty state */
.fo-empty { display: flex; align-items: center; justify-content: center; padding: 80px 40px; text-align: center; }
.fo-empty-k { font-family: var(--fo-mono); font-size: 10px; letter-spacing: 0.16em; color: var(--fo-text-mute); margin-bottom: 12px; text-transform: uppercase; }
.fo-empty-h { font-size: 16px; color: var(--fo-text-dim); line-height: 1.5; margin-bottom: 16px; }
</style>"""


# ---------------------------------------------------------------------------
# HTML renderers
# ---------------------------------------------------------------------------

def _render_queue_html(fails, selected_idx):
    rows = []
    for i, f in enumerate(fails):
        fail_id = f.get("_id", f"FID-{10000 + i}")
        ticker = _ticker(f["cusip"])
        tier = f["priority_tier"]
        tl = tier.lower()
        tier_short = tier[:4] if len(tier) > 4 else tier
        category = CATEGORY_DISPLAY.get(f["category"], f["category"])
        prime = _is_prime(f["firm_name"])
        sel = "is-sel" if i == selected_idx else ""

        cov = min(f["inv_coverage_pct"], 100)
        spark_w = max(2, int(cov * 44 / 100))
        spark_c = "var(--fo-ok)" if cov >= 70 else "var(--fo-warn)" if cov >= 40 else "var(--fo-crit)"

        rsd = _reg_sho_days(f)
        rs_cell = f'<span class="fo-rs-pill">T-{rsd}d</span>' if rsd else '<span style="color:var(--fo-text-mute)">—</span>'

        flags = f.get("flags", [])
        fchips = "".join(f'<span class="fo-fchip">{_esc(fl)}</span>' for fl in flags[:2])
        fmore = f'<span class="fo-fchip-more">+{len(flags) - 2}</span>' if len(flags) > 2 else ""

        firm_short = f["firm_name"][:22]

        rows.append(f"""<tr class="{sel}">
<td><span class="fo-tdot tier-{tl}"></span><span class="fo-tn tier-{tl}">{_esc(tier_short)}</span></td>
<td class="r">{f['priority_score']:.0f}</td>
<td>{_esc(fail_id)}</td>
<td><div class="fo-sym">{_esc(ticker)}</div><div class="fo-cusip">{_esc(f['cusip'])}</div></td>
<td>{_esc(category)}</td>
<td><span class="fo-cp-dot {'prime' if prime else 'exec'}"></span><span style="font-size:10.5px">{_esc(firm_short)}</span></td>
<td style="color:var(--fo-text-dim)">{_esc(f['account'])}</td>
<td class="r">{f['ftd_qty']:,}</td>
<td class="r">{_fmt_mv(f['market_value'])}</td>
<td class="r"><span class="fo-age-pill {_age_cls(f['age_days'])}">{f['age_days']}d</span></td>
<td>{rs_cell}</td>
<td><div class="fo-cov-wrap"><div class="fo-spark" style="width:44px;height:4px"><div class="fo-spark-fill" style="width:{spark_w}px;background:{spark_c}"></div></div><span class="fo-cov-n">{f['inv_coverage_pct']}%</span></div></td>
<td><div class="fo-fchips">{fchips}{fmore}</div></td>
<td><span class="fo-ai-pending">○</span></td>
</tr>""")

    return f"""<div class="fo-queue-head">
<span class="fo-panel-title">FAIL QUEUE</span>
<span class="fo-panel-sub">{len(fails)} fails</span>
</div>
<div class="fo-queue-scroll">
<table class="fo-qtab">
<thead><tr>
<th>TIER</th><th class="r">PRI</th><th>ID</th><th>SECURITY</th><th>TYPE</th>
<th>COUNTERPARTY</th><th>ACCT</th><th class="r">SHARES</th><th class="r">NOTIONAL</th>
<th class="r">AGE</th><th>REG SHO</th><th>COVERAGE</th><th>FLAGS</th><th>AI</th>
</tr></thead>
<tbody>{"".join(rows)}</tbody>
</table></div>"""


def _render_stage1_html(fail, triage_data, is_ai=False):
    t = triage_data or fail.get("triage", {})
    reason = t.get("reason") or "—"
    esc_level = (t.get("escalation_level") or "NONE").upper()
    esc_text = ESCALATION_DISPLAY_FULL.get(esc_level, esc_level)
    action = t.get("action") or "—"
    deadline = t.get("deadline") or "—"
    category = CATEGORY_DISPLAY.get(t.get("category", ""), t.get("category")) or "—"
    lifecycle = t.get("lifecycle_state") or "—"
    source_label = "AI Model" if is_ai else "Generated"

    flags = t.get("flags", [])
    ftags = ""
    if flags:
        ftags = '<div class="fo-flag-wrap" style="margin-top:10px">' + "".join(
            f'<span class="fo-flag-tag">{_esc(FLAG_DISPLAY.get(fl.upper() if isinstance(fl, str) else fl, fl))}</span>'
            for fl in flags
        ) + "</div>"

    return f"""<div class="fo-stage-card">
<header class="fo-stage-head">
<div class="fo-stage-num">01</div>
<div><div class="fo-stage-title">TRIAGE MODEL</div><div class="fo-stage-sub">Prioritization · Tier · Flags</div></div>
<div style="margin-left:auto;font-family:var(--fo-mono);font-size:9.5px;color:var(--fo-text-mute)">{source_label}</div>
</header>
<div class="fo-assessment">{_esc(reason)}</div>
<div class="fo-kv-grid">
<div class="fo-kv"><span class="k">Escalation</span><span class="v">{_esc(esc_text)}</span></div>
<div class="fo-kv"><span class="k">Action</span><span class="v">{_esc(action)}</span></div>
<div class="fo-kv"><span class="k">Category</span><span class="v">{_esc(category)}</span></div>
<div class="fo-kv"><span class="k">Lifecycle</span><span class="v">{_esc(lifecycle)}</span></div>
<div class="fo-kv"><span class="k">Deadline</span><span class="v">{_esc(deadline)}</span></div>
<div class="fo-kv"><span class="k">Account</span><span class="v">{_esc(fail['account'])}</span></div>
</div>{ftags}</div>"""


def _render_stage2_html(fail, resolver_data, dtc_map):
    r = resolver_data
    gridlock = r.get("gridlock_detected", False)
    if gridlock:
        parties = r.get("gridlock_parties", [])
        pnames = [_dtc_to_firm(p, dtc_map) for p in parties]
        ptxt = ", ".join(pnames) if pnames else "multiple firms"
        banner = f'<div class="fo-banner crit">GRIDLOCK DETECTED — coordinated outreach to {_esc(ptxt)} required.</div>'
    else:
        banner = '<div class="fo-banner ok">No gridlock detected. Resolution path is unblocked.</div>'

    steps = r.get("resolution_steps", [])
    steps_html = ""
    if steps:
        items = ""
        for step in steps:
            num = step.get("step", "?")
            action = step.get("action", "UNKNOWN").upper()
            atxt = ACTION_DISPLAY.get(action, action)
            qty = step.get("qty", 0) or 0
            dtc_code = step.get("dtc", "")
            firm = _dtc_to_firm(dtc_code, dtc_map) if dtc_code else ""
            ftxt = f" ({_esc(firm)})" if firm and firm != dtc_code else ""
            items += f'<li><span class="fo-step-n">{str(num).zfill(2)}</span><span class="fo-step-t">{_esc(atxt)} — {qty:,} shares from {_esc(dtc_code)}{ftxt}</span></li>'
        steps_html = f'<div class="fo-steps-title">RECOMMENDED RESOLUTION STEPS</div><ol class="fo-steps">{items}</ol>'

    fb = r.get("fallback_strategy")
    fb_html = ""
    if fb:
        fb_text = FALLBACK_DISPLAY.get(fb, fb.lower().replace("_", " "))
        fb_qty = r.get("fallback_qty", 0) or 0
        sfb = r.get("secondary_fallback")
        parts = [f"If primary steps are insufficient: {fb_text}"]
        if fb_qty:
            parts[0] += f" for {fb_qty:,} shares"
        if sfb:
            sfb_text = FALLBACK_DISPLAY.get(sfb, sfb.lower().replace("_", " "))
            sfb_qty = r.get("secondary_fallback_qty", 0) or 0
            sfb_part = f"If still unresolved: {sfb_text}"
            if sfb_qty:
                sfb_part += f" for {sfb_qty:,} shares"
            parts.append(sfb_part)
        fb_html = f'<div class="fo-subhead">FALLBACK STRATEGY</div><div class="fo-prose">{_esc(". ".join(parts) + ".")}</div>'

    narrative = r.get("narrative", "")
    narr_html = ""
    if narrative:
        narr_html = f'<div class="fo-subhead">MODEL NARRATIVE</div><div class="fo-prose">{_esc(narrative)}</div>'

    esc_req = r.get("escalation_required", False)
    esc_reason = r.get("escalation_reason", "")
    if esc_req:
        reason_txt = f" — {_esc(esc_reason)}" if esc_reason else ""
        esc_html = f'<div class="fo-banner warn" style="margin-top:12px">Escalation required{reason_txt}</div>'
    else:
        esc_html = '<div class="fo-banner ok" style="margin-top:12px">No escalation required at this tier.</div>'

    total_cov = r.get("total_coverable", 0) or 0
    ftd = fail["ftd_qty"]
    cov_pct = round(total_cov / ftd * 100, 1) if ftd > 0 else 0
    residual = r.get("residual_short", 0) or 0

    cov_color = "var(--fo-ok)" if cov_pct >= 100 else "var(--fo-warn)" if cov_pct >= 75 else "var(--fo-crit)"
    cov_summary = f"""<div style="display:grid;grid-template-columns:1fr 1fr;gap:0;margin:12px 0;background:var(--fo-panel);border:1px solid var(--fo-hair);border-radius:3px">
<div style="padding:10px 12px;border-right:1px solid var(--fo-hair);text-align:center">
<div style="font-family:var(--fo-mono);font-size:24px;font-weight:500;color:{cov_color}">{cov_pct}%</div>
<div style="font-family:var(--fo-mono);font-size:9px;color:var(--fo-text-mute);letter-spacing:0.1em;text-transform:uppercase;margin-top:2px">Total Coverage</div>
</div>
<div style="padding:10px 12px;text-align:center">
<div style="font-family:var(--fo-mono);font-size:24px;font-weight:500;color:var(--fo-text)">{residual:,}</div>
<div style="font-family:var(--fo-mono);font-size:9px;color:var(--fo-text-mute);letter-spacing:0.1em;text-transform:uppercase;margin-top:2px">Residual Short</div>
</div></div>"""

    return f"""<div class="fo-stage-card">
<header class="fo-stage-head">
<div class="fo-stage-num">02</div>
<div><div class="fo-stage-title">RESOLUTION MODEL</div><div class="fo-stage-sub">Action plan · Fallback · Narrative</div></div>
<div style="margin-left:auto;font-family:var(--fo-mono);font-size:9.5px;color:var(--fo-text-mute)">AI Model</div>
</header>
{banner}{steps_html}{cov_summary}{fb_html}{narr_html}{esc_html}</div>"""


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="FinOps Resolver — Post-Trade Fail Desk",
    page_icon="F",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(THEME_CSS, unsafe_allow_html=True)

# ---- Initialise defaults ----
if "ollama_url" not in st.session_state:
    st.session_state["ollama_url"] = "http://localhost:11434"
if "fail_count" not in st.session_state:
    st.session_state["fail_count"] = 10
if "filter_val" not in st.session_state:
    st.session_state["filter_val"] = "ALL"
if "stage_mode" not in st.session_state:
    st.session_state["stage_mode"] = "Both"
if "batch_results" not in st.session_state:
    st.session_state["batch_results"] = {}

fails = st.session_state.get("fails", [])

# ---- Empty state ----
if not fails:
    st.markdown(
        '<div class="fo-empty"><div>'
        '<div class="fo-empty-k">NO FAIL DATA</div>'
        '<div class="fo-empty-h">Generate settlement fail scenarios to begin analysis.</div>'
        '</div></div>',
        unsafe_allow_html=True,
    )
    gc1, gc2, gc3 = st.columns([1, 0.5, 1])
    with gc2:
        fail_count = st.slider("Fails to Generate", min_value=1, max_value=50, value=10, key="fail_count_init")
        if st.button("GENERATE FAILS", type="primary", use_container_width=True):
            fails_list, dtc_map = generate_fails(fail_count)
            for i, f in enumerate(fails_list):
                f["_id"] = f"FID-{10000 + i}"
            st.session_state["fails"] = _sort_fails(fails_list)
            st.session_state["dtc_firm_map"] = dtc_map
            st.session_state["batch_results"] = {}
            for _k in ("batch_running", "batch_idx", "batch_total", "batch_times", "batch_errors", "cancel_batch"):
                st.session_state.pop(_k, None)
            st.rerun()
    st.stop()

# ---- Top bar ----
conn = st.session_state.get("conn")
ollama_url = st.session_state.get("ollama_url", "localhost:11434")
ollama_ok = conn is not None and conn["reachable"] and not conn["models_missing"]
ollama_reachable = conn is not None and conn["reachable"]
time_str = datetime.utcnow().strftime("%H:%M:%S")

st.markdown(
    f'<div class="fo-topbar">'
    f'<div class="fo-brand">'
    f'<div class="fo-brand-mark">F</div>'
    f'<div><div class="fo-brand-name">FINOPS RESOLVER</div>'
    f'<div class="fo-brand-sub">POST-TRADE FAILS · INTERNAL</div></div></div>'
    f'<div class="fo-top-right"><div class="fo-status-cluster">'
    f'<div class="fo-status-item">'
    f'<span class="fo-dot {"ok" if ollama_ok else "warn"}"></span>'
    f'<span class="fo-label">MODEL</span>'
    f'<span class="fo-val">triage · resolver</span></div>'
    f'<div class="fo-status-item">'
    f'<span class="fo-dot {"ok" if ollama_reachable else "warn"}"></span>'
    f'<span class="fo-label">OLLAMA</span>'
    f'<span class="fo-val">{_esc(ollama_url)}</span></div>'
    f'<div class="fo-status-item">'
    f'<span class="fo-label">UTC</span>'
    f'<span class="fo-val">{time_str}</span></div>'
    f'</div></div></div>',
    unsafe_allow_html=True,
)

# ---- Controls bar ----
ctrl_c1, ctrl_c2, ctrl_c3, ctrl_c4, ctrl_c5 = st.columns([0.5, 1.5, 1.2, 0.6, 0.5])

with ctrl_c1:
    fail_count = st.number_input(
        "Count", min_value=1, max_value=50, value=10, key="fail_count",
        label_visibility="collapsed",
    )
    if st.button("GENERATE", type="primary", use_container_width=True):
        fails_list, dtc_map = generate_fails(fail_count)
        for i, f in enumerate(fails_list):
            f["_id"] = f"FID-{10000 + i}"
        st.session_state["fails"] = _sort_fails(fails_list)
        st.session_state["dtc_firm_map"] = dtc_map
        st.session_state.pop("triage_result", None)
        st.session_state.pop("triage_fail_id", None)
        st.session_state.pop("resolver_result", None)
        st.session_state.pop("resolver_fail_id", None)
        st.session_state["batch_results"] = {}
        for _k in ("batch_running", "batch_idx", "batch_total", "batch_times", "batch_errors", "cancel_batch"):
            st.session_state.pop(_k, None)
        st.rerun()

with ctrl_c2:
    st.radio(
        "Filter",
        ["ALL", "CRITICAL", "HIGH", "MEDIUM", "LOW", "REG SHO", "GRIDLOCK"],
        horizontal=True,
        key="filter_val",
        label_visibility="collapsed",
    )

with ctrl_c3:
    st.radio(
        "Stage",
        ["Both", "Stage 1", "Stage 2"],
        horizontal=True,
        key="stage_mode",
        label_visibility="collapsed",
    )

with ctrl_c4:
    if st.session_state.get("batch_running"):
        def _cancel_batch():
            st.session_state["cancel_batch"] = True
        st.button("■ CANCEL", on_click=_cancel_batch, use_container_width=True)
    else:
        if st.button("▶ ANALYZE ALL", use_container_width=True, key="analyze_all"):
            st.session_state["batch_running"] = True
            st.session_state["batch_idx"] = 0
            st.session_state["batch_total"] = len(fails)
            st.session_state["batch_times"] = []
            st.session_state["batch_errors"] = 0
            st.session_state["cancel_batch"] = False
            st.rerun()

with ctrl_c5:
    conn_btn = st.button("TEST OLLAMA", use_container_width=True)
    if conn_btn:
        st.session_state["conn"] = check_ollama_connection(st.session_state["ollama_url"])
        st.rerun()

# ---- Batch progress ----
_batch_msg = st.session_state.pop("batch_complete_msg", None)
if _batch_msg:
    if "cancelled" in _batch_msg:
        st.warning(_batch_msg)
    else:
        st.success(_batch_msg)

if st.session_state.get("batch_running") and not st.session_state.get("cancel_batch"):
    _bi = st.session_state.get("batch_idx", 0)
    _bt = st.session_state.get("batch_total", 1)
    _btimes = st.session_state.get("batch_times", [])
    _pct = _bi / _bt if _bt > 0 else 0
    _eta = ""
    if _btimes:
        _avg_s = sum(_btimes) / len(_btimes)
        _rem_s = (_bt - _bi) * _avg_s
        _eta = f" · ~{int(_rem_s // 60)}:{int(_rem_s % 60):02d} remaining"
    _finfo = ""
    if _bi < len(fails):
        _cf = fails[_bi]
        _finfo = f" — {_cf['cusip']} ({_ticker(_cf['cusip'])})"
    st.progress(_pct, text=f"Analyzing fail {_bi + 1}/{_bt}{_finfo}{_eta}")

# ---- KPI strip ----
total = len(fails)
notional = sum(f["market_value"] for f in fails)

_br_all = st.session_state.get("batch_results", {})
_ai_triage = {fid: r for fid, r in _br_all.items() if r.get("triage", {}).get("ok")}
_ai_resolver = {fid: r for fid, r in _br_all.items() if r.get("resolver", {}).get("ok")}
_has_ai = len(_ai_triage) > 0

if _has_ai:
    critical = sum(
        1 for r in _ai_triage.values()
        if (r["triage"]["data"].get("priority_tier") or "").upper() == "CRITICAL"
    )
    critical_val = str(critical)
    critical_cls = " crit" if critical > 0 else ""
    critical_sub = f"{round(critical / len(_ai_triage) * 100)}% of {len(_ai_triage)} analyzed"
else:
    critical_val = "—"
    critical_cls = ""
    critical_sub = "run AI pipeline"

if _ai_resolver:
    escalate = sum(
        1 for r in _ai_resolver.values()
        if r["resolver"]["data"].get("escalation_required")
    )
    escalate_val = str(escalate)
    escalate_cls = " warn" if escalate > 5 else ""
    escalate_sub = f"of {len(_ai_resolver)} resolved"
else:
    escalate_val = "—"
    escalate_cls = ""
    escalate_sub = "run AI pipeline"

if _ai_resolver:
    _fmap = {f["_id"]: f for f in fails}
    _covs = []
    for fid, r in _ai_resolver.items():
        _tc = r["resolver"]["data"].get("total_coverable", 0) or 0
        _fl = _fmap.get(fid)
        if _fl and _fl["ftd_qty"] > 0:
            _covs.append(_tc / _fl["ftd_qty"] * 100)
    avg_cov = round(sum(_covs) / len(_covs)) if _covs else 0
    avg_cov_val = f"{avg_cov}%"
    avg_cov_sub = "healthy inventory" if avg_cov >= 60 else "thin inventory"
else:
    avg_cov_val = "—"
    avg_cov_sub = "run AI pipeline"

if _ai_resolver:
    gridlock_n = sum(
        1 for r in _ai_resolver.values()
        if r["resolver"]["data"].get("gridlock_detected")
    )
    gridlock_val = str(gridlock_n)
    gridlock_cls = " warn" if gridlock_n > 0 else ""
    gridlock_sub = "chain-match needed"
else:
    gridlock_val = "—"
    gridlock_cls = ""
    gridlock_sub = "run AI pipeline"

if _has_ai:
    regsho_n = sum(
        1 for r in _ai_triage.values()
        if any(
            fl.upper() in ("REG_SHO", "REG_SHO_CLOSE_OUT", "REG_SHO_CLOSEOUT")
            for fl in r["triage"]["data"].get("flags", [])
        )
    )
    regsho_val = str(regsho_n)
    regsho_cls = " crit" if regsho_n > 0 else ""
    regsho_sub = "close-out eligible"
else:
    regsho_val = "—"
    regsho_cls = ""
    regsho_sub = "run AI pipeline"

st.markdown(
    f'<div class="fo-kpis">'
    f'<div class="fo-kpi"><div class="fo-kpi-label">OPEN FAILS</div>'
    f'<div class="fo-kpi-val">{total}</div><div class="fo-kpi-sub">monitored</div></div>'
    f'<div class="fo-kpi"><div class="fo-kpi-label">CRITICAL</div>'
    f'<div class="fo-kpi-val{critical_cls}">{critical_val}</div>'
    f'<div class="fo-kpi-sub">{critical_sub}</div></div>'
    f'<div class="fo-kpi"><div class="fo-kpi-label">NEEDS ESCALATION</div>'
    f'<div class="fo-kpi-val{escalate_cls}">{escalate_val}</div>'
    f'<div class="fo-kpi-sub">{escalate_sub}</div></div>'
    f'<div class="fo-kpi"><div class="fo-kpi-label">AVG COVERAGE</div>'
    f'<div class="fo-kpi-val">{avg_cov_val}</div>'
    f'<div class="fo-kpi-sub">{avg_cov_sub}</div></div>'
    f'<div class="fo-kpi"><div class="fo-kpi-label">GRIDLOCK</div>'
    f'<div class="fo-kpi-val{gridlock_cls}">{gridlock_val}</div>'
    f'<div class="fo-kpi-sub">{gridlock_sub}</div></div>'
    f'<div class="fo-kpi"><div class="fo-kpi-label">REG SHO</div>'
    f'<div class="fo-kpi-val{regsho_cls}">{regsho_val}</div>'
    f'<div class="fo-kpi-sub">{regsho_sub}</div></div>'
    f'<div class="fo-kpi"><div class="fo-kpi-label">NOTIONAL EXPOSURE</div>'
    f'<div class="fo-kpi-val">{_fmt_mv(notional)}</div>'
    f'<div class="fo-kpi-sub">across open book</div></div>'
    f'</div>',
    unsafe_allow_html=True,
)

# ---- Apply filter ----
filtered = _apply_filter(fails, st.session_state.get("filter_val", "ALL"))
if not filtered:
    st.info("No fails match the selected filter.")
    st.stop()

# ---- Two-pane layout ----
left_col, right_col = st.columns([1.1, 1], gap="small")

with left_col:
    st.markdown(
        f'<div class="fo-queue-head">'
        f'<span class="fo-panel-title">FAIL QUEUE</span>'
        f'<span class="fo-panel-sub">{len(filtered)} fails</span></div>',
        unsafe_allow_html=True,
    )
    queue_rows = []
    _br_q = st.session_state.get("batch_results", {})
    for i, f in enumerate(filtered):
        rsd = _reg_sho_days(f)
        fid = f.get("_id", f"FID-{10000 + i}")
        _st = _br_q.get(fid, {}).get("status", "")
        if _st == "analyzed":
            ai_label = "✓ Analyzed"
        elif _st == "triage_error":
            ai_label = "✗ Triage Err"
        elif _st == "resolver_error":
            ai_label = "⚠ Resolve Err"
        elif _st == "triage_only":
            ai_label = "½ Triage"
        else:
            ai_label = "○ Pending"
        queue_rows.append({
            "TIER": f["priority_tier"],
            "PRI": int(f["priority_score"]),
            "ID": fid,
            "TICKER": _ticker(f["cusip"]),
            "CUSIP": f["cusip"],
            "TYPE": CATEGORY_DISPLAY.get(f["category"], f["category"]),
            "COUNTERPARTY": "vs CNS" if f["firm_name"] == "CNS" else f["firm_name"],
            "ACCT": f["account"],
            "SHARES": f["ftd_qty"],
            "NOTIONAL": f["market_value"],
            "AGE": f["age_days"],
            "REG SHO": f"T-{rsd}d" if rsd else "—",
            "COV%": f["inv_coverage_pct"],
            "FLAGS": ", ".join(f.get("flags", [])[:3]),
            "STATUS": ai_label,
        })
    queue_df = pd.DataFrame(queue_rows)
    event = st.dataframe(
        queue_df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key="queue_selection",
        column_config={
            "PRI": st.column_config.NumberColumn(width="small"),
            "SHARES": st.column_config.NumberColumn(format="%d"),
            "NOTIONAL": st.column_config.NumberColumn(format="$%,.0f"),
            "AGE": st.column_config.NumberColumn(width="small"),
            "COV%": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%d%%"),
            "STATUS": st.column_config.TextColumn(width="small"),
        },
    )
    sel_rows = event.selection.rows
    selected_idx = sel_rows[0] if sel_rows else 0

with right_col:
    fail = filtered[selected_idx]
    fail_id = fail.get("_id", f"FID-{selected_idx}")

    # ---- Detail header ----
    ticker, name = CUSIP_INFO.get(fail["cusip"], (fail["cusip"][:4], fail["cusip"]))
    tier = fail["priority_tier"]
    tl = tier.lower()
    category_disp = CATEGORY_DISPLAY.get(fail["category"], fail["category"])
    prime = _is_prime(fail["firm_name"])
    rsd = _reg_sho_days(fail)
    rs_chip = f'<span class="fo-chip fo-chip-regsho">REG SHO · T-{rsd}d</span>' if rsd else ""
    gl_chip = '<span class="fo-chip fo-chip-gridlock">GRIDLOCK</span>' if _has_gridlock(fail) else ""

    st.markdown(
        f'<div class="fo-detail-head">'
        f'<div class="fo-fid-row">'
        f'<span class="fo-fid-label">FAIL</span>'
        f'<span class="fo-fid-value">{_esc(fail_id)}</span>'
        f'<span class="fo-chip tier-{tl}">{_esc(tier)}</span>'
        f'{rs_chip}{gl_chip}</div>'
        f'<div class="fo-fail-title">{_esc(category_disp)} · {_esc(ticker)}'
        f'<span style="color:var(--fo-text-dim);font-weight:400;font-size:13px;margin-left:8px">{_esc(name)}</span></div>'
        f'<div class="fo-fail-sub">'
        f'{fail["ftd_qty"]:,} sh · {_fmt_mv(fail["market_value"])} notional'
        f'<span style="margin:0 8px;color:var(--fo-text-mute)">·</span>'
        f'{"vs CNS" if fail["firm_name"] == "CNS" else _esc(fail["firm_name"]) + (" (PB)" if prime else " (Exec)")}'
        f'<span style="margin:0 8px;color:var(--fo-text-mute)">·</span>'
        f'{_esc(fail["account"])}'
        f'<span style="margin:0 8px;color:var(--fo-text-mute)">·</span>'
        f'CUSIP {_esc(fail["cusip"])}</div></div>',
        unsafe_allow_html=True,
    )

    # ---- Metric strip ----
    score = fail["priority_score"]
    pk = _pri_cls(score)
    cov = fail["inv_coverage_pct"]
    cov_c = "var(--fo-ok)" if cov >= 70 else "var(--fo-warn)" if cov >= 40 else "var(--fo-crit)"
    age = fail["age_days"]
    age_lbl = "past SLA" if age >= 10 else "critical band" if age >= 7 else "in window"
    esc_lvl = fail["triage"]["escalation_level"]
    esc_txt = ESCALATION_DISPLAY.get(esc_lvl, esc_lvl)

    fail_flags = fail.get("flags", [])
    ftags = "".join(
        f'<span class="fo-flag-tag">{_esc(FLAG_DISPLAY.get(fl, fl))}</span>'
        for fl in fail_flags
    )

    st.markdown(
        f'<div class="fo-mstrip" style="grid-template-columns:repeat(5,1fr) 1.5fr">'
        f'<div class="fo-ms"><div class="fo-ms-l">PRIORITY</div>'
        f'<div class="fo-ms-v {pk}" style="font-size:32px">{score:.0f}</div>'
        f'<div class="fo-ms-s">of 100</div></div>'
        f'<div class="fo-ms"><div class="fo-ms-l">TIER</div>'
        f'<div class="fo-ms-v {pk}">{_esc(tier)}</div>'
        f'<div class="fo-ms-s">{_esc(esc_txt)}</div></div>'
        f'<div class="fo-ms"><div class="fo-ms-l">AGE</div>'
        f'<div class="fo-ms-v">{age}<span class="sm"> d</span></div>'
        f'<div class="fo-ms-s">{age_lbl}</div></div>'
        f'<div class="fo-ms"><div class="fo-ms-l">COVERAGE</div>'
        f'<div class="fo-ms-v">{cov}<span class="sm"> %</span></div>'
        f'<div class="fo-cov-bar"><div class="fo-cov-bar-fill" style="width:{min(cov, 100)}%;background:{cov_c}"></div></div></div>'
        f'<div class="fo-ms"><div class="fo-ms-l">REG SHO</div>'
        f'<div class="fo-ms-v">{"T-" + str(rsd) + "d" if rsd else "—"}</div>'
        f'<div class="fo-ms-s">{"close-out window" if rsd else "no deadline"}</div></div>'
        f'<div class="fo-ms"><div class="fo-ms-l">FLAGS</div>'
        f'<div class="fo-flag-wrap">{ftags}</div></div></div>',
        unsafe_allow_html=True,
    )

    # ---- Stage cards ----
    sm = st.session_state.get("stage_mode", "Both")
    show_s1 = sm in ("Both", "Stage 1")
    show_s2 = sm in ("Both", "Stage 2")

    _br_detail = st.session_state.get("batch_results", {}).get(fail_id, {})

    triage_result = st.session_state.get("triage_result")
    triage_fail_id = st.session_state.get("triage_fail_id")
    _indiv_triage = (
        triage_result is not None
        and triage_result.get("ok")
        and triage_fail_id == fail_id
    )
    has_ai_triage = _indiv_triage or _br_detail.get("triage", {}).get("ok", False)
    eff_triage = triage_result if _indiv_triage else _br_detail.get("triage") if has_ai_triage else None

    resolver_result = st.session_state.get("resolver_result")
    resolver_fail_id = st.session_state.get("resolver_fail_id")
    _indiv_resolver = (
        resolver_result is not None
        and resolver_result.get("ok")
        and resolver_fail_id == fail_id
    )
    has_ai_resolver = _indiv_resolver or _br_detail.get("resolver", {}).get("ok", False)
    eff_resolver = resolver_result if _indiv_resolver else _br_detail.get("resolver") if has_ai_resolver else None

    if show_s1 and show_s2:
        sc1, sc2 = st.columns(2)
    elif show_s1:
        sc1 = st.container()
        sc2 = None
    else:
        sc1 = None
        sc2 = st.container()

    # -- Stage 1 --
    if show_s1 and sc1 is not None:
        with sc1:
            tdata = eff_triage["data"] if has_ai_triage else fail.get("triage", {})
            st.markdown(
                _render_stage1_html(fail, tdata, is_ai=has_ai_triage),
                unsafe_allow_html=True,
            )
            if not has_ai_triage:
                if st.button("▶  RUN STAGE 1: TRIAGE", key="run_triage", use_container_width=True):
                    if not _is_connected():
                        st.warning("Test your Ollama connection first (TEST OLLAMA button).")
                    else:
                        with st.spinner("Stage 1: Analyzing fail record..."):
                            result = call_triage(st.session_state["ollama_url"], fail)
                        if result["ok"]:
                            st.session_state["triage_result"] = result
                            st.session_state["triage_fail_id"] = fail_id
                            _br_u = st.session_state["batch_results"]
                            if fail_id not in _br_u:
                                _br_u[fail_id] = {}
                            _br_u[fail_id]["triage"] = result
                            if _br_u[fail_id].get("status") != "analyzed":
                                _br_u[fail_id]["status"] = "triage_only"
                            st.rerun()
                        else:
                            st.error(result["error"])
            if has_ai_triage and eff_triage:
                with st.expander("DEBUG: TRIAGE PROMPT"):
                    st.code(eff_triage.get("raw_prompt", ""), language="text")
                with st.expander("DEBUG: RAW TRIAGE RESPONSE"):
                    st.code(eff_triage.get("raw_content", ""), language="json")

    # -- Stage 2 --
    if show_s2 and sc2 is not None:
        with sc2:
            if has_ai_resolver and eff_resolver:
                dtc_map = st.session_state.get("dtc_firm_map", {})
                st.markdown(
                    _render_stage2_html(fail, eff_resolver["data"], dtc_map),
                    unsafe_allow_html=True,
                )
                with st.expander("DEBUG: RESOLVER PROMPT"):
                    st.code(eff_resolver.get("raw_prompt", ""), language="json")
                with st.expander("DEBUG: RAW RESOLVER RESPONSE"):
                    st.code(eff_resolver.get("raw_content", ""), language="text")
            elif has_ai_triage:
                st.markdown(
                    '<div class="fo-stage-card">'
                    '<header class="fo-stage-head">'
                    '<div class="fo-stage-num">02</div>'
                    '<div><div class="fo-stage-title">RESOLUTION MODEL</div>'
                    '<div class="fo-stage-sub">Action plan · Fallback · Narrative</div></div>'
                    '</header>'
                    '<div class="fo-assessment" style="color:var(--fo-text-mute)">'
                    'Stage 1 triage complete. Run Stage 2 to generate the resolution plan.</div></div>',
                    unsafe_allow_html=True,
                )
                if st.button("▶  RUN STAGE 2: RESOLUTION", key="run_resolver", use_container_width=True):
                    if not _is_connected():
                        st.warning("Test your Ollama connection first (TEST OLLAMA button).")
                    else:
                        t_data = eff_triage["data"]
                        with st.spinner("Stage 2: Generating resolution plan..."):
                            res_result = call_resolver(
                                st.session_state["ollama_url"], fail, t_data
                            )
                        if res_result["ok"]:
                            st.session_state["resolver_result"] = res_result
                            st.session_state["resolver_fail_id"] = fail_id
                            _br_u2 = st.session_state["batch_results"]
                            if fail_id not in _br_u2:
                                _br_u2[fail_id] = {}
                            _br_u2[fail_id]["resolver"] = res_result
                            _br_u2[fail_id]["status"] = "analyzed"
                            st.rerun()
                        else:
                            st.error(res_result["error"])
            else:
                st.markdown(
                    '<div class="fo-stage-card">'
                    '<header class="fo-stage-head">'
                    '<div class="fo-stage-num">02</div>'
                    '<div><div class="fo-stage-title">RESOLUTION MODEL</div>'
                    '<div class="fo-stage-sub">Action plan · Fallback · Narrative</div></div>'
                    '</header>'
                    '<div class="fo-assessment" style="color:var(--fo-text-mute)">'
                    'Run Stage 1 first to enable resolution planning.</div></div>',
                    unsafe_allow_html=True,
                )

    # ---- AI Reasoning Trace ----
    if has_ai_resolver and eff_resolver:
        thinking = eff_resolver.get("thinking")
        if thinking:
            with st.expander("VIEW AI REASONING TRACE"):
                lines = thinking.strip().split("\n")
                trace_html = "".join(
                    f'<div class="fo-trace-line">'
                    f'<span class="fo-trace-n">{str(i + 1).zfill(2)}</span>'
                    f'<span class="fo-trace-t">{_esc(line)}</span></div>'
                    for i, line in enumerate(lines) if line.strip()
                )
                st.markdown(
                    f'<div class="fo-trace-body">{trace_html}</div>',
                    unsafe_allow_html=True,
                )

# ---- Status bar ----
_analyzed_count = sum(1 for r in st.session_state.get("batch_results", {}).values() if r.get("status") == "analyzed")
st.markdown(
    f'<div class="fo-statusbar">'
    f'<span>ENV</span> <span class="v">prod-replica</span>'
    f'<span style="margin:0 6px">·</span>'
    f'<span>DATA</span> <span class="v">synthetic · {len(fails)} fails</span>'
    f'<span style="margin:0 6px">·</span>'
    f'<span>PIPELINE</span> <span class="v">triage → resolver · {_analyzed_count}/{len(fails)} analyzed</span>'
    f'<span style="flex:1"></span>'
    f'<span class="v">controls above queue</span>'
    f'</div>',
    unsafe_allow_html=True,
)

# ---- Batch auto-processing ----
if st.session_state.get("batch_running") and st.session_state.get("cancel_batch"):
    _bi_c = st.session_state.get("batch_idx", 0)
    _bt_c = st.session_state.get("batch_total", 0)
    _be_c = st.session_state.get("batch_errors", 0)
    _msg_c = f"Batch cancelled — {_bi_c}/{_bt_c} completed"
    if _be_c:
        _msg_c += f", {_be_c} errors"
    st.session_state["batch_complete_msg"] = _msg_c
    st.session_state["batch_running"] = False
    st.session_state["cancel_batch"] = False
    st.rerun()
elif st.session_state.get("batch_running"):
    _bi_p = st.session_state.get("batch_idx", 0)
    _bt_p = st.session_state.get("batch_total", 0)

    if _bi_p < _bt_p and _bi_p < len(fails):
        _fail_p = fails[_bi_p]
        _fid_p = _fail_p["_id"]
        _t0 = time.time()
        _entry = {}

        _tres = call_triage(st.session_state["ollama_url"], _fail_p)
        if _tres["ok"]:
            _entry["triage"] = _tres
            _rres = call_resolver(
                st.session_state["ollama_url"], _fail_p, _tres["data"]
            )
            if _rres["ok"]:
                _entry["resolver"] = _rres
                _entry["status"] = "analyzed"
            else:
                _entry["status"] = "resolver_error"
                _entry["error"] = _rres["error"]
                st.session_state["batch_errors"] = st.session_state.get("batch_errors", 0) + 1
        else:
            _entry["status"] = "triage_error"
            _entry["error"] = _tres["error"]
            st.session_state["batch_errors"] = st.session_state.get("batch_errors", 0) + 1

        st.session_state["batch_times"].append(time.time() - _t0)
        st.session_state["batch_results"][_fid_p] = _entry
        st.session_state["batch_idx"] = _bi_p + 1
        st.rerun()
    else:
        _be_d = st.session_state.get("batch_errors", 0)
        _msg_d = f"Batch complete — {_bt_p}/{_bt_p} analyzed"
        if _be_d:
            _msg_d += f", {_be_d} errors"
        st.session_state["batch_complete_msg"] = _msg_d
        st.session_state["batch_running"] = False
        st.rerun()
