"""
Decision log — append-only record of analysis findings and optimization actions.
Each run adds a new entry so we can track changes over time.
"""
import json, os
from datetime import datetime

SCRIPT_DIR = os.path.dirname(__file__)
OUT_DIR = os.path.join(SCRIPT_DIR, "out")
LOG_PATH = os.path.join(OUT_DIR, "decision_log.jsonl")

def log_analysis(cross_json_path=None, auto_append=True):
    """Read cross_analysis.json and append a decision log entry."""
    if cross_json_path is None:
        cross_json_path = os.path.join(OUT_DIR, "cross_analysis.json")

    if not os.path.exists(cross_json_path):
        print(f"Cross analysis not found: {cross_json_path}")
        return None

    with open(cross_json_path, encoding="utf-8") as f:
        cross = json.load(f)

    entry = {
        "timestamp": datetime.now().isoformat(),
        "summary": cross.get("summary", {}),
        "harvest_actions": cross.get("harvest_actions", [])[:10],
        "negate_actions": cross.get("negate_actions", [])[:10],
        "gateway_asins": [
            {"asin": a.get("asin"), "sku": a.get("sku"), "action": a.get("action")}
            for a in cross.get("gateway_asin_final", []) if a.get("is_gateway")
        ],
        "account_health": cross.get("summary", {}).get("account_health", {}),
    }

    # Read history
    history = []
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        history.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

    # Compute diff from previous run
    prev_spend = history[-1]["summary"]["total_spend"] if history else 0
    prev_sales = history[-1]["summary"]["total_sales"] if history else 0
    curr_spend = entry["summary"]["total_spend"]
    curr_sales = entry["summary"]["total_sales"]

    entry["diff"] = {
        "spend_change": round(curr_spend - prev_spend, 2),
        "sales_change": round(curr_sales - prev_sales, 2),
        "prev_entry_count": len(history),
    }

    if auto_append:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        print(f"[OK] Decision log appended: {LOG_PATH} (entry #{len(history) + 1})")

    return entry

if __name__ == "__main__":
    entry = log_analysis()
    if entry:
        h = entry.get("account_health", {})
        print(f"\n===== 决策日志 =====")
        print(f"  条目: #{entry['diff']['prev_entry_count'] + 1}")
        print(f"  健康度: {h.get('score', '?')}/100 ({h.get('grade', '?')})")
        print(f"  花费: ${entry['summary']['total_spend']:,.2f}")
        print(f"  销售: ${entry['summary']['total_sales']:,.2f}")
        print(f"  混合ACOS: {entry['summary'].get('blended_acos', 0):.1%}" if entry['summary'].get('blended_acos') else "")