"""Centralized threshold configuration for ad analysis.
All values can be overridden per account via advertise/config/<account>.json.
"""
import json
import os

# ── Default thresholds (industry defaults, calibrated for Home & Garden) ──

# Campaign-level
HIGH_ACOS_THRESHOLD = 0.40        # ACOS above this = flagged as high risk
LOW_ROAS_THRESHOLD = 2.5           # ROAS below this = flagged as problem
WINNER_ACOS_THRESHOLD = 0.15       # ACOS below this + sales > 0 = "winner"
BUDGET_UTILIZATION_IDEAL_MIN = 0.70  # Minimum ideal budget utilization
BUDGET_UTILIZATION_IDEAL_MAX = 0.90  # Maximum ideal budget utilization

# Search term classification
MIN_ORDERS_HARVEST = 2             # Minimum orders for Harvest bucket
MAX_ACOS_HARVEST = 0.30            # Maximum ACOS for Harvest bucket
MIN_CLICKS_NEGATE = 15             # Minimum clicks for Negate bucket
MIN_SPEND_NEGATE = 2.0             # Minimum spend for Negate bucket
MAX_CLICKS_MONITOR = 15            # Click ceiling for Monitor bucket
MAX_SPEND_IGNORE = 1.0             # Spend ceiling for Ignore bucket
MAX_CLICKS_IGNORE = 5              # Click ceiling for Ignore bucket

# Attribution
ATTRIBUTION_WINDOW_DAYS = 7        # SP attribution window
MIN_REPORT_DAYS = 14               # Minimum days for reliable analysis

# Placement bid recommendations
PLACEMENT_ACOS_GOOD = 0.20         # ACOS below this = recommend raise bid
PLACEMENT_CVR_GOOD = 0.05          # CVR above this with good ACOS = raise bid
PLACEMENT_ACOS_BAD = 0.40          # ACOS above this = recommend lower bid
PLACEMENT_CVR_BAD = 0.02           # CVR below this = check creative relevance
PLACEMENT_MIN_SPEND = 100.0        # Minimum spend for placement recommendation
PLACEMENT_RAISE_PCT = (10, 20)     # Raise bid by 10-20%
PLACEMENT_LOWER_PCT = (15, 30)     # Lower bid by 15-30%

# ASIN-level
ASIN_SPEND_REDLINE = 100.0         # ASIN spending > this with 0 sales = pause
ASIN_ZERO_SALE_DAYS = 30           # Days with 0 sales before recommending pause

# Targeting
TARGETING_MIN_SPEND = 1.0          # Minimum spend for zero-conversion flag
TARGETING_TOP_N = 20               # Number of top/bottom targets to show

# Brand keywords (override per account)
BRAND_TERMS = ["senight", "snight", "rucen"]
COMPETITOR_BRANDS = [
    "tempur", "sealy", "simmons", "serta", "purple", "casper", "nectar",
    "tuft & needle", "leesa", "layla", "bear", "helix", "brooklyn bedding",
    "saatva", "avocado", "boll & branch", "parachute", "brooklinen",
    "linenspa", "zinus", "classic brands", "sleep number",
]
PROTECTED_TERMS = set()  # terms that should never be negated (fill per account)

# Category classification roots
JUNK_ROOTS = [
    "cheap", "free", "used", "refurbished", "broken", "damaged", "diy",
    "how to", "instructions", "manual", "repair", "replacement parts",
    "warranty", "recall", "scam", "fake", "counterfeit",
    "pet", "dog", "cat", "car", "truck", "rv", "boat", "camping",
    "outdoor furniture cover", "patio furniture cover",
    "medical", "hospital", "nursing", "hotel", "motel", "airbnb",
    "wholesale", "bulk", "pallet",
]
CATEGORY_ROOTS = [
    "pillow", "cushion", "mattress", "topper", "protector", "bedding",
    "bed", "headboard", "frame", "sheet", "comforter", "duvet", "blanket",
    "throw", "sham", "cover", "case", "wedge", "bolster", "lumbar",
    "memory foam", "gel", "cooling", "bamboo", "cotton", "down",
    "sleep", "sleeping", "nap", "rest",
]


def load_account_config(account_name):
    """Load account-specific threshold overrides from config/{account}.json."""
    config_path = os.path.join(os.path.dirname(__file__), "config", f"{account_name}.json")
    if not os.path.exists(config_path):
        return {}
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def apply_account_overrides(account_name):
    """Apply account-specific overrides to module-level threshold constants."""
    cfg = load_account_config(account_name)
    if not cfg:
        return

    t = cfg.get("thresholds", {})
    globals_dict = globals()

    mapping = {
        "high_acos": "HIGH_ACOS_THRESHOLD",
        "low_roas": "LOW_ROAS_THRESHOLD",
        "winner_acos": "WINNER_ACOS_THRESHOLD",
        "min_orders_harvest": "MIN_ORDERS_HARVEST",
        "max_acos_harvest": "MAX_ACOS_HARVEST",
        "min_clicks_negate": "MIN_CLICKS_NEGATE",
        "min_spend_negate": "MIN_SPEND_NEGATE",
    }
    for cfg_key, var_name in mapping.items():
        if cfg_key in t:
            globals_dict[var_name] = t[cfg_key]

    if "brand_terms" in cfg:
        globals_dict["BRAND_TERMS"] = cfg["brand_terms"]
    if "competitor_brands" in cfg:
        globals_dict["COMPETITOR_BRANDS"] = cfg["competitor_brands"]
    if "protected_terms" in cfg:
        globals_dict["PROTECTED_TERMS"] = set(cfg["protected_terms"])
