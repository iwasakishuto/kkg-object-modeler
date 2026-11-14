"""Build every trial script with solidcraft-cli and compare the bodies with expected.json.

    python examples/kkg-trial/check.py [path/to/solidcraft-cli]

Writes out/<script>.step / .glb / .png and out/report.json. The expected values
come from generate.py (the schedule dimensions), never from SolidCraft's output.
"""

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CLI = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "target" / "release" / "solidcraft-cli.exe"
OUT = HERE / "out"
OUT.mkdir(exist_ok=True)
expected = json.loads((HERE / "expected.json").read_text(encoding="utf-8"))


def run(args):
    p = subprocess.run([str(CLI), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, p.stdout, p.stderr


def bodies_of(measure):
    # eval prints {bodies: [{name, volume, bbox, ...}], ...}; accept a few shapes.
    if isinstance(measure, dict):
        for key in ("bodies", "measure"):
            if key in measure:
                return bodies_of(measure[key])
    if isinstance(measure, list):
        return {b.get("name"): b for b in measure if isinstance(b, dict)}
    return {}


report = {}
for name, exp in expected.items():
    script = HERE / f"{name}.json"
    rec = {"source": exp.get("_source")}
    code, _, err = run(["run", str(script), "--out", str(OUT / f"{name}.step"), "--out", str(OUT / f"{name}.glb"), "--timings", "--quiet"])
    rec["run_exit"] = code
    if code != 0:
        rec["run_error"] = err.strip()[-2000:]
    code, _, err = run(["eval", str(script), "--json-out", str(OUT / f"{name}.measure.json")])
    rec["eval_exit"] = code
    if code != 0:
        rec["eval_error"] = err.strip()[-2000:]
        report[name] = rec
        continue
    got = bodies_of(json.loads((OUT / f"{name}.measure.json").read_text(encoding="utf-8")))
    rows = []
    for body, e in exp.items():
        if body.startswith("_"):
            continue
        g = got.get(body)
        row = {"body": body, "expected_volume": round(e["volume"], 1)}
        if g is None:
            row["status"] = "missing"
        else:
            v = g.get("volume_mm3", g.get("volume"))
            row["volume"] = v
            row["error_pct"] = None if v is None else round(100 * (v - e["volume"]) / e["volume"], 4)
            if "bbox" in e:
                row["expected_bbox"] = e["bbox"]
                bb = g.get("bbox") or {}
                row["bbox"] = [bb.get("min"), bb.get("max")]
        rows.append(row)
    rec["bodies"] = rows
    rec["extra_bodies"] = sorted(set(got) - set(k for k in exp if not k.startswith("_")))
    code, _, err = run(["snapshot", str(script), "--out", str(OUT / f"{name}.png"), "--view", "iso", "--width", "1200", "--height", "800", "--no-grid"])
    rec["snapshot_exit"] = code
    if code != 0:
        rec["snapshot_error"] = err.strip()[-1000:]
    report[name] = rec

(OUT / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
print(json.dumps({k: {"run": v.get("run_exit"), "eval": v.get("eval_exit"), "missing": [r["body"] for r in v.get("bodies", []) if r.get("error_pct") is None], "worst_pct": max((abs(r.get("error_pct") or 0) for r in v.get("bodies", [])), default=None)} for k, v in report.items()}, indent=1))
