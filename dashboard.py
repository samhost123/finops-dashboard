"""FinOps Resolver — Executive Dashboard (Phase 0: Data Generation & Display)"""

import json
import random
import re
import string
from datetime import date

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

# Top-broker DTC numbers from triage CLAUDE.md (40% of assignments)
TOP_BROKER_DTCS = [
    "0005", "0050", "0062", "0089", "0161", "0164", "0188",
    "0226", "0235", "0352", "0385", "0417", "0443", "0499", "0551",
]

# Well-known real CUSIPs for realistic display
CUSIP_POOL = [
    "594918104",  # MSFT
    "037833100",  # AAPL
    "67066G104",  # NVDA
    "02079K107",  # GOOG
    "023135106",  # AMZN
    "30231G102",  # META
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

    firm_name = _pick_firm(category, cp_dtc, dtc_firm_map)
    inventory = generate_inventory()

    for ftr in ftrs:
        if ftr["dtc"] not in dtc_firm_map:
            dtc_firm_map[ftr["dtc"]] = random.choice(EXECUTION_BROKERS)

    related_fails = generate_related_fails(ftrs)
    for rf in related_fails:
        if rf["dtc"] not in dtc_firm_map:
            dtc_firm_map[rf["dtc"]] = random.choice(EXECUTION_BROKERS)

    # Escalation risk label
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
        "category": triage["category"],
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

    if category == "CNS_FAIL":
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
# Streamlit UI
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="FinOps Settlement Dashboard",
    page_icon="\U0001f4ca",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---- Sidebar ----
with st.sidebar:
    st.header("Configuration")
    st.text_input(
        "Ollama Endpoint",
        value="http://localhost:11434",
        key="ollama_url",
        help="URL of the Ollama instance hosting finops-triage and finops-resolver models.",
    )

    # -- Connection status --
    test_btn = st.button("Test Connection", use_container_width=True)
    if test_btn:
        st.session_state["conn"] = check_ollama_connection(st.session_state["ollama_url"])

    conn = st.session_state.get("conn")
    if conn is not None:
        if conn["reachable"] and not conn["models_missing"]:
            st.success("Connected — both models available")
        elif conn["reachable"] and conn["models_missing"]:
            for m in conn["models_missing"]:
                st.warning(f"{m} is not installed. Run:  `ollama pull {m}`")
            if conn["models_found"]:
                st.info(f"Available: {', '.join(conn['models_found'])}")
        else:
            st.error(conn["error"])

    st.divider()
    fail_count = st.slider(
        "Fails to Generate",
        min_value=1,
        max_value=50,
        value=10,
        key="fail_count",
    )
    generate_btn = st.button("Generate Fails", type="primary", use_container_width=True)

# ---- Title ----
st.title("Settlement Fail Resolution Dashboard")
st.caption("Two-model AI pipeline: Triage → Resolver")

# ---- Generate on button click ----
if generate_btn:
    fails_generated, dtc_firm_map = generate_fails(fail_count)
    st.session_state["fails"] = fails_generated
    st.session_state["dtc_firm_map"] = dtc_firm_map
    st.session_state.pop("triage_result", None)
    st.session_state.pop("triage_fail_idx", None)
    st.session_state.pop("resolver_result", None)
    st.session_state.pop("resolver_fail_idx", None)

fails = st.session_state.get("fails", [])

# ---- Summary Metrics ----
col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total Fails", len(fails) if fails else 0)
col2.metric("Critical Priority", "—", help="Available after batch analysis")
col3.metric("Escalation Required", "—", help="Available after batch analysis")
col4.metric("Avg Coverage", "—", help="Available after batch analysis")
col5.metric("Gridlock Detected", "—", help="Available after batch analysis")

st.divider()

# ---- Raw Data Table ----
if fails:
    rows = []
    for f in fails:
        rows.append({
            "Security": f["cusip"],
            "Counterparty": f["firm_name"],
            "Account": f["account"],
            "Fail Type": CATEGORY_DISPLAY.get(f["category"], f["category"]),
            "Shares": f"{f['ftd_qty']:,}",
            "Market Value": _format_market_value(f["market_value"]),
            "Age (Days)": f["age_days"],
            "Reg SHO": "Yes" if f["reg_sho"] else "No",
            "Inventory": f"{f['inv_coverage_pct']}%",
        })

    df = pd.DataFrame(rows)

    def _color_age(row):
        age = row["Age (Days)"]
        if age >= 10:
            return ["background-color: #3b1219; color: #fca5a5"] * len(row)
        elif age >= 7:
            return ["background-color: #3b2408; color: #fcd34d"] * len(row)
        elif age >= 4:
            return ["background-color: #0b3d2e; color: #6ee7b7"] * len(row)
        else:
            return ["background-color: #0d2818; color: #86efac"] * len(row)

    styled = df.style.apply(_color_age, axis=1).set_properties(
        **{"text-align": "left"}
    )

    st.subheader("Generated Fail Scenarios")
    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        height=min(len(fails) * 40 + 50, 600),
    )

    # ---- Row Selection ----
    st.divider()
    labels = [
        f"{i+1}. {f['cusip']} — {f['firm_name']} — {CATEGORY_DISPLAY.get(f['category'], f['category'])}"
        for i, f in enumerate(fails)
    ]
    selected_idx = st.selectbox(
        "Select a fail to analyze",
        range(len(fails)),
        format_func=lambda i: labels[i],
        key="selected_fail_idx",
    )
    selected_fail = fails[selected_idx]

    # ---- Stage 1: Triage ----
    run_triage_btn = st.button("Run Stage 1: Triage", type="primary")

    if run_triage_btn:
        if not _is_connected():
            st.warning("Please test your Ollama connection in the sidebar before running analysis.")
        else:
            with st.spinner("Stage 1: Analyzing fail record..."):
                result = call_triage(st.session_state["ollama_url"], selected_fail)
            if result["ok"]:
                st.session_state["triage_result"] = result
                st.session_state["triage_fail_idx"] = selected_idx
            else:
                st.error(result["error"])

    # ---- Debug Expanders ----
    triage_result = st.session_state.get("triage_result")
    triage_fail_idx = st.session_state.get("triage_fail_idx")

    if triage_result and triage_fail_idx == selected_idx:
        with st.expander("Debug: Selected Fail Verification"):
            st.write(f"**Dropdown index:** {selected_idx}")
            st.write(f"**Stored triage_fail_idx:** {triage_fail_idx}")
            st.write(f"**CUSIP:** {selected_fail['cusip']}")
            st.write(f"**Firm:** {selected_fail['firm_name']}")
            st.write(f"**Category:** {selected_fail['category']}")
            st.write(f"**Generated priority_tier:** {selected_fail['priority_tier']}")
            st.write(f"**Generated priority_score:** {selected_fail['priority_score']}")
            st.write(f"**Age:** {selected_fail['age_days']}d | Market Value: {_format_market_value(selected_fail['market_value'])}")
            st.write(f"**Reg SHO:** {selected_fail['reg_sho']} | Inv Coverage: {selected_fail['inv_coverage_pct']}% | CP Fail Rate: {selected_fail['cp_fail_rate_pct']}%")

        with st.expander("Debug: Triage Prompt"):
            st.code(triage_result.get("raw_prompt", "(not captured)"), language="text")

        with st.expander("Debug: Raw Triage Response"):
            st.code(triage_result.get("raw_content", "(not captured)"), language="json")

    # ---- Display Triage Results ----
    if triage_result and triage_result["ok"] and triage_fail_idx == selected_idx:
        t = triage_result["data"]
        st.divider()
        st.subheader("Stage 1: Triage Results")

        # Priority score + tier
        score = t.get("priority_score", 0)
        tier = t.get("priority_tier", "UNKNOWN").upper()

        if score > 75:
            score_color = "#fca5a5"
        elif score > 50:
            score_color = "#fcd34d"
        else:
            score_color = "#6ee7b7"

        tier_colors = {
            "CRITICAL": ("#3b1219", "#fca5a5"),
            "HIGH": ("#3b2408", "#fcd34d"),
            "MEDIUM": ("#0b3d2e", "#6ee7b7"),
            "LOW": ("#0d2818", "#86efac"),
        }
        tier_bg, tier_fg = tier_colors.get(tier, ("#161B22", "#E6EDF3"))

        col_score, col_tier, col_esc = st.columns(3)
        with col_score:
            st.markdown(
                f"<div style='text-align:center'>"
                f"<span style='font-size:3rem;font-weight:700;color:{score_color}'>{score}</span>"
                f"<br><span style='color:#8b949e'>Priority Score</span></div>",
                unsafe_allow_html=True,
            )
        with col_tier:
            st.markdown(
                f"<div style='text-align:center;padding-top:0.5rem'>"
                f"<span style='background:{tier_bg};color:{tier_fg};padding:0.4rem 1.2rem;"
                f"border-radius:6px;font-size:1.2rem;font-weight:600'>"
                f"{TIER_DISPLAY.get(tier, tier)}</span>"
                f"<br><br><span style='color:#8b949e'>Priority Tier</span></div>",
                unsafe_allow_html=True,
            )
        with col_esc:
            esc_level = t.get("escalation_level", "NONE").upper()
            esc_text = ESCALATION_DISPLAY_FULL.get(esc_level, esc_level)
            st.markdown(
                f"<div style='text-align:center;padding-top:0.8rem'>"
                f"<span style='font-size:1.3rem;font-weight:600;color:#E6EDF3'>{esc_text}</span>"
                f"<br><span style='color:#8b949e'>Escalation Level</span></div>",
                unsafe_allow_html=True,
            )

        # Reason
        reason = t.get("reason", "")
        if reason:
            st.markdown(f"**Assessment:** {reason}")

        # Deadline
        deadline = t.get("deadline")
        if deadline:
            st.markdown(f"**Close-out deadline:** {deadline}")

        # Flags
        flags = t.get("flags", [])
        if flags:
            tag_html = " ".join(
                f"<span style='background:#21262d;color:#c9d1d9;padding:0.25rem 0.6rem;"
                f"border-radius:12px;font-size:0.85rem;margin-right:0.3rem'>"
                f"{FLAG_DISPLAY.get(f.upper() if isinstance(f, str) else f, f)}</span>"
                for f in flags
            )
            st.markdown(f"**Flags:** {tag_html}", unsafe_allow_html=True)

        # ---- Stage 2: Resolver ----
        st.divider()
        run_resolver_btn = st.button("Run Stage 2: Resolution", type="primary")

        if run_resolver_btn:
            if not _is_connected():
                st.warning(
                    "Please test your Ollama connection in the sidebar before running analysis."
                )
            else:
                with st.spinner("Stage 2: Generating resolution plan..."):
                    res_result = call_resolver(
                        st.session_state["ollama_url"], selected_fail, t
                    )
                if res_result["ok"]:
                    st.session_state["resolver_result"] = res_result
                    st.session_state["resolver_fail_idx"] = selected_idx
                else:
                    st.error(res_result["error"])

        # ---- Debug Expanders (Stage 2) ----
        resolver_result = st.session_state.get("resolver_result")
        resolver_fail_idx = st.session_state.get("resolver_fail_idx")

        if resolver_result and resolver_fail_idx == selected_idx:
            with st.expander("Debug: Resolver Prompt"):
                st.code(
                    resolver_result.get("raw_prompt", "(not captured)"),
                    language="json",
                )

            with st.expander("Debug: Raw Resolver Response"):
                st.code(
                    resolver_result.get("raw_content", "(not captured)"),
                    language="text",
                )

            if resolver_result.get("ok"):
                with st.expander("Debug: Parsed Resolver JSON"):
                    st.json(resolver_result["data"])

        # ---- Display Resolver Results ----
        if (
            resolver_result
            and resolver_result.get("ok")
            and resolver_fail_idx == selected_idx
        ):
            r = resolver_result["data"]
            dtc_map = st.session_state.get("dtc_firm_map", {})

            st.divider()
            st.subheader("Pipeline Flow: Triage → Resolution")

            thinking = resolver_result.get("thinking")
            if thinking:
                with st.expander("View AI Reasoning"):
                    st.markdown(thinking)

            left_col, right_col = st.columns(2)

            with left_col:
                st.markdown("#### Stage 1: Triage")
                st.markdown(f"**Priority Score:** {t.get('priority_score', '—')}")
                st.markdown(
                    f"**Priority Tier:** "
                    f"{TIER_DISPLAY.get(t.get('priority_tier', '').upper(), t.get('priority_tier', '—'))}"
                )
                esc_lvl = t.get("escalation_level", "NONE").upper()
                st.markdown(
                    f"**Escalation:** {ESCALATION_DISPLAY_FULL.get(esc_lvl, esc_lvl)}"
                )
                triage_flags = t.get("flags", [])
                if triage_flags:
                    st.markdown(
                        "**Flags:** "
                        + ", ".join(
                            FLAG_DISPLAY.get(fl.upper() if isinstance(fl, str) else fl, fl)
                            for fl in triage_flags
                        )
                    )

            with right_col:
                st.markdown("#### Stage 2: Resolution")
                steps = r.get("resolution_steps", [])
                st.markdown(f"**Steps:** {len(steps)}")
                total_cov = r.get("total_coverable", 0) or 0
                ftd = selected_fail["ftd_qty"]
                cov_pct = round(total_cov / ftd * 100, 1) if ftd > 0 else 0
                st.markdown(
                    f"**Coverage:** {cov_pct}% ({total_cov:,} / {ftd:,} shares)"
                )
                st.markdown(
                    f"**Gridlock:** {'Yes' if r.get('gridlock_detected') else 'No'}"
                )
                st.markdown(
                    f"**Escalation:** "
                    f"{'Required' if r.get('escalation_required') else 'Not required'}"
                )

            # Resolution Steps
            st.divider()
            st.subheader("Resolution Steps")

            for step in steps:
                step_num = step.get("step", "?")
                action = step.get("action", "UNKNOWN").upper()
                action_text = ACTION_DISPLAY.get(action, action)
                qty = step.get("qty", 0) or 0
                dtc_code = step.get("dtc", "")
                firm = _dtc_to_firm(dtc_code, dtc_map) if dtc_code else ""
                stype = step.get("settlement_type", "")
                sdate = step.get("settlement_date", "")
                coverage = step.get("coverage_after_step_pct", 0) or 0
                remaining = step.get("remaining_short", 0) or 0
                rationale = step.get("rationale", "")

                firm_text = f" ({firm})" if firm and firm != dtc_code else ""
                detail_parts = []
                if stype:
                    detail_parts.append(stype)
                if sdate:
                    detail_parts.append(sdate)
                detail_text = (
                    f" [{', '.join(detail_parts)}]" if detail_parts else ""
                )

                st.markdown(
                    f"**Step {step_num}:** {action_text} — "
                    f"{qty:,} shares from {dtc_code}{firm_text}{detail_text}"
                )
                if rationale:
                    st.caption(rationale)
                st.progress(
                    min(coverage / 100, 1.0),
                    text=f"Coverage: {coverage}% | Remaining: {remaining:,} shares",
                )

            # Coverage Summary
            st.divider()
            total_cov = r.get("total_coverable", 0) or 0
            ftd = selected_fail["ftd_qty"]
            cov_pct = round(total_cov / ftd * 100, 1) if ftd > 0 else 0
            residual = r.get("residual_short", 0) or 0

            cov_col, res_col = st.columns(2)
            with cov_col:
                if cov_pct >= 100:
                    cov_color = "#6ee7b7"
                elif cov_pct >= 75:
                    cov_color = "#fcd34d"
                else:
                    cov_color = "#fca5a5"
                st.markdown(
                    f"<div style='text-align:center'>"
                    f"<span style='font-size:2.5rem;font-weight:700;color:{cov_color}'>"
                    f"{cov_pct}%</span>"
                    f"<br><span style='color:#8b949e'>Total Coverage</span></div>",
                    unsafe_allow_html=True,
                )
            with res_col:
                st.markdown(
                    f"<div style='text-align:center'>"
                    f"<span style='font-size:2.5rem;font-weight:700;color:#E6EDF3'>"
                    f"{residual:,}</span>"
                    f"<br><span style='color:#8b949e'>Residual Short</span></div>",
                    unsafe_allow_html=True,
                )

            st.progress(min(cov_pct / 100, 1.0))

            # Gridlock Banner
            gridlock = r.get("gridlock_detected", False)
            gridlock_parties = r.get("gridlock_parties", [])
            if gridlock:
                party_names = [_dtc_to_firm(p, dtc_map) for p in gridlock_parties]
                party_text = ", ".join(party_names) if party_names else "multiple firms"
                st.error(
                    f"Delivery gridlock detected involving {len(gridlock_parties)} "
                    f"firms: {party_text}. Coordinated outreach recommended."
                )
            else:
                st.success("No gridlock detected")

            # Escalation Banner
            esc_req = r.get("escalation_required", False)
            esc_reason = r.get("escalation_reason")
            if esc_req:
                reason_text = f" — {esc_reason}" if esc_reason else ""
                st.warning(f"Escalation required{reason_text}")
            else:
                st.success("No escalation required")

            # Fallback Strategy
            fb = r.get("fallback_strategy")
            fb_qty = r.get("fallback_qty", 0) or 0
            sfb = r.get("secondary_fallback")
            sfb_qty = r.get("secondary_fallback_qty", 0) or 0

            if fb:
                fb_text = FALLBACK_DISPLAY.get(fb, fb.lower().replace("_", " "))
                parts = [f"If primary steps are insufficient: {fb_text}"]
                if fb_qty:
                    parts[0] += f" for {fb_qty:,} shares"
                if sfb:
                    sfb_text = FALLBACK_DISPLAY.get(
                        sfb, sfb.lower().replace("_", " ")
                    )
                    sfb_part = f"If still unresolved: {sfb_text}"
                    if sfb_qty:
                        sfb_part += f" for {sfb_qty:,} shares"
                    parts.append(sfb_part)
                st.markdown(
                    "**Fallback Strategy:** " + ". ".join(parts) + "."
                )

            # Narrative
            narrative = r.get("narrative")
            if narrative:
                st.divider()
                st.subheader("Resolution Summary")
                st.markdown(narrative)

else:
    st.info("Use the sidebar to generate settlement fail scenarios.")
