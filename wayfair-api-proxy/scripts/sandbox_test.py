import json
import os
import sys
import urllib.error
import urllib.request

SANDBOX_URL = "https://api.wayfair.io/sandbox/v1/supplier-order-api/graphql"

QUERY = """
query($supplierId: Int!, $filter: InventoryFilterInput, $page: InventoryPageInput) {
  inventorySummaryList(supplierId: $supplierId, filter: $filter, page: $page) {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        supplierPartNumber
        sku
        inventoryPosition {
          castleGate {
            onHandQty
            onHand { allocatedQty inStockQty }
            warehouses { warehouseId onHandQty }
          }
        }
      }
    }
  }
}
"""


def main() -> int:
    token = os.getenv("WAYFAIR_SANDBOX_TOKEN", "")
    supplier_id = os.getenv("WAYFAIR_SUPPLIER_ID", "")
    part_numbers = os.getenv("WAYFAIR_PART_NUMBERS", "").strip()

    if not token:
        print("FAIL: set WAYFAIR_SANDBOX_TOKEN (Developer Portal sandbox token)")
        return 1
    if not supplier_id.isdigit():
        print("FAIL: set WAYFAIR_SUPPLIER_ID (integer parent supplier ID)")
        return 1

    variables = {
        "supplierId": int(supplier_id),
        "page": {"first": 10, "after": None},
    }
    if part_numbers:
        variables["filter"] = {
            "supplierPartNumbers": [p.strip() for p in part_numbers.split(",") if p.strip()]
        }

    request = urllib.request.Request(
        SANDBOX_URL,
        data=json.dumps({"query": QUERY, "variables": variables}).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token,
        },
    )
    try:
        response = urllib.request.urlopen(request, timeout=40)
        payload = json.load(response)
        status = response.status
    except urllib.error.HTTPError as exc:
        print("HTTP", exc.code)
        return 1
    except Exception as exc:
        print("NET", type(exc).__name__)
        return 1

    errors = [str(item.get("message", ""))[:240] for item in payload.get("errors") or []]
    result = ((payload.get("data") or {}).get("inventorySummaryList")) or {}
    edges = result.get("edges") or []

    print("STATUS", status)
    print("errors", errors)
    print("pageInfo", result.get("pageInfo"))
    print("nodes", len(edges))

    if edges:
        node = edges[0].get("node") or {}
        castle_gate = ((node.get("inventoryPosition") or {}).get("castleGate")) or {}
        print(
            "first_node_has_sku",
            bool(node.get("sku") or node.get("supplierPartNumber")),
            "castleGate_fields",
            sorted(castle_gate),
            "warehouses",
            len(castle_gate.get("warehouses") or []),
        )

    if status == 200 and not errors and edges:
        print("SANDBOX OK: check Developer Portal → Sandbox Testing; it should turn Done within ~30s")
        return 0
    print("SANDBOX NOT PASSED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
