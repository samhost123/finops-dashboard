"""FinOps Resolver — Executive Dashboard (Phase 0: Data Generation & Display)"""

import random
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
# Firm name pool — bulge bracket + market makers + regionals
# ---------------------------------------------------------------------------

FIRM_NAMES = [
    # Bulge bracket / major banks
    "Goldman Sachs", "Morgan Stanley", "JPMorgan",
    "Bank of America Securities", "Citigroup Global Markets",
    "Barclays Capital", "Deutsche Bank Securities", "UBS Securities",
    "Credit Suisse", "Wells Fargo Securities",
    "BNP Paribas Securities", "Societe Generale",
    "Nomura Securities", "HSBC Securities", "Jefferies",
    "RBC Capital Markets", "TD Securities", "Mizuho Securities",
    "MUFG Securities",
    # Market makers / regional broker-dealers
    "Citadel Securities", "Virtu Financial", "Jane Street",
    "Two Sigma", "Susquehanna", "Optiver",
    "IMC Financial Markets", "Flow Traders", "Wolverine Trading",
    "DRW Securities", "Knight Capital", "Cantor Fitzgerald",
    "Piper Sandler", "Raymond James", "Baird", "Oppenheimer",
    "Cowen", "Needham", "Stifel", "Janney Montgomery Scott",
    "Ladenburg Thalmann", "National Securities", "Maxim Group",
    "B. Riley Securities", "Aegis Capital", "Benchmark Company",
    "Chardan Capital", "EF Hutton", "H.C. Wainwright",
    "Roth Capital Partners",
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
    """Assign firm names to DTC numbers. Top brokers get bulge-bracket names."""
    mapping = {}
    shuffled_firms = FIRM_NAMES.copy()
    random.shuffle(shuffled_firms)
    for i, dtc in enumerate(TOP_BROKER_DTCS):
        mapping[dtc] = shuffled_firms[i % len(shuffled_firms)]
    return mapping, shuffled_firms


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


def generate_fail(dtc_firm_map, firm_pool):
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

    # Resolve firm name
    if cp_dtc in dtc_firm_map:
        firm_name = dtc_firm_map[cp_dtc]
    else:
        firm_name = random.choice(firm_pool)
        dtc_firm_map[cp_dtc] = firm_name

    triage = generate_triage_multi_category(ftd_qty, ftrs)
    inventory = generate_inventory()

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
    }


def generate_fails(count):
    dtc_firm_map, firm_pool = _build_dtc_firm_map()
    return [generate_fail(dtc_firm_map, firm_pool) for _ in range(count)]


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
    st.session_state["fails"] = generate_fails(fail_count)

fails = st.session_state.get("fails", [])

# ---- Summary Metrics ----
col1, col2, col3, col4, col5 = st.columns(5)
if fails:
    critical_count = sum(1 for f in fails if f["priority_tier"] == "CRITICAL")
    high_count = sum(1 for f in fails if f["priority_tier"] == "HIGH")
    escalation_count = sum(1 for f in fails if f["escalation_risk"] == "High")
    gridlock_count = 0  # Phase 3+
    avg_coverage = 0.0  # Phase 3+
    col1.metric("Total Fails", len(fails))
    col2.metric("Critical Priority", critical_count)
    col3.metric("Escalation Required", escalation_count)
    col4.metric("Avg Coverage", f"{avg_coverage:.0f}%")
    col5.metric("Gridlock Detected", gridlock_count)
else:
    col1.metric("Total Fails", 0)
    col2.metric("Critical Priority", 0)
    col3.metric("Escalation Required", 0)
    col4.metric("Avg Coverage", "0%")
    col5.metric("Gridlock Detected", 0)

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
            "Priority Tier": TIER_DISPLAY.get(f["priority_tier"], f["priority_tier"]),
            "Escalation Risk": f["escalation_risk"],
        })

    df = pd.DataFrame(rows)

    def _color_tier(row):
        tier = row["Priority Tier"]
        if tier == "Critical":
            return ["background-color: #3b1219; color: #fca5a5"] * len(row)
        elif tier == "High":
            return ["background-color: #3b2408; color: #fcd34d"] * len(row)
        elif tier == "Medium":
            return ["background-color: #0b3d2e; color: #6ee7b7"] * len(row)
        else:
            return ["background-color: #0d2818; color: #86efac"] * len(row)

    styled = df.style.apply(_color_tier, axis=1).set_properties(
        **{"text-align": "left"}
    )

    st.subheader("Generated Fail Scenarios")
    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        height=min(len(fails) * 40 + 50, 600),
    )
else:
    st.info("Use the sidebar to generate settlement fail scenarios.")
