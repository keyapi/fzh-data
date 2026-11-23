"""Developer tool: build the split private replay pack (no data committed)."""
from __future__ import annotations
import hashlib, json, zipfile
from pathlib import Path

AN = Path("D:/Work/fzh-order-store/analysis")
FILES = {
    "D3b_v3_11.xlsx": AN / "D3b-v3_11-20261112/D_历史归一与回测_D3b_v3_11_2026-11-12.xlsx",
    "D5_v6_8.xlsx": AN / "D5v6_8-poland/D_概率与服务_D5_v6_8_2026-11-11.xlsx",
    "D6_v6_22.xlsx": AN / "D6v6_22-1111/D_Top50沙盒_D6_v6_22_2026-11-11.xlsx",
    "D6_v6_24.xlsx": AN / "D6v6_24-1112/D_Top50沙盒_D6_v6_24_2026-11-12.xlsx",
    "E_nodes.parquet": AN / "E_v2_20261111/E_nodes_20261111.parquet",
    "E_lifecycle.parquet": AN / "E_v2_20261111/E_lifecycle_20261111.parquet",
    "C14.xlsx": AN / "C-refresh-20261110/通途库存_A337_v15_refresh_2026-11-10.xlsx",
    "CNY_v13.xlsx": AN / "S2_9-delivery-final-20261106/D_春节排期优化_2026-11-11_v13.xlsx",
    "traj_v13.xlsx": AN / "S2_9-delivery-final-20261106/D_统一逐日轨迹_2026-11-11_v13.xlsx",
    "W1_SO.jsonl": Path("D:/Work/fzh-order-store/w1_supply_facts_v2/supply_facts_raw.jsonl"),
    "sku_map.tsv": Path("D:/Work/fzh-order-store/sku_map.tsv"),
    "USNJ_recommend.csv": AN / "usnj_replenishment_pilot_20261112/USNJ补货建议.csv",
    "boss_v5.5.xlsx": AN / "D_老板版补货建议_2026-11-11_v5.5.xlsx",
    "DEMAND_TREND.csv": AN / "DEMAND_TREND_20261112.csv",
    "service_policy.csv": AN / "service-policy-20261112/service_policy_20261112.csv",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main(out_dir="D:/private/demand", version="2026-11-13.1", part_size=8_500_000):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    zip_path = out / f"supply-copilot-pack-{version}.zip"
    entries = []
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, src in FILES.items():
            if not src.exists():
                raise SystemExit(f"missing source: {src}")
            data = src.read_bytes()
            z.writestr(f"data/{name}", data)
            entries.append({"path": f"data/{name}", "sha256": sha(data), "size": len(data)})
    blob = zip_path.read_bytes()
    parts = []
    for index, start in enumerate(range(0, len(blob), part_size)):
        chunk = blob[start:start + part_size]
        part = out / f"supply-copilot-pack-{version}.part{index:03d}"
        part.write_bytes(chunk)
        parts.append({"name": part.name, "sha256": sha(chunk), "size": len(chunk),
                      "file_url": f"/private/files/{part.name}"})
    manifest = {"schema": "supply-copilot-pack/v1", "version": version,
                "as_of": "2026-11-13", "files": entries, "parts": parts,
                "combined_sha256": sha(blob), "zip_size": len(blob)}
    (out / f"manifest-{version}.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (Path(__file__).resolve().parent / "pack_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"zip": str(zip_path), "zip_size": len(blob), "parts": len(parts),
                      "manifest": str(out / f"manifest-{version}.json")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
