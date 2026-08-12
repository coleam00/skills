"""Token accounting, on from the first run. FACTORY_RULES.md 8.

Instrumented on day one rather than added after the first surprising invoice, because
cost projections for this are wrong by 10-20x in the same direction every time. One
"implement an issue" run is five agent sessions plus a mutation suite plus a soak, and
from the outside it looks like one prompt.

    python factory/cost.py record <run-id>          # fold node usage into the run record
    python factory/cost.py report                   # per-run and per-node totals

Node usage is read from .factory/runs/<run>/nodes/*.json, which each node writes from the
`--output-format json` envelope its agent returns. No estimation, no modelling: if a
number is not measured it is not reported, because an invented cost figure is worse than
no cost figure -- it gets believed.
"""
from __future__ import annotations
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = os.path.join(ROOT, ".factory", "runs")


def node_usage(run: str) -> list[dict]:
    out = []
    for path in sorted(glob.glob(os.path.join(RUNS, run, "nodes", "*.json"))):
        try:
            with open(path, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        u = d.get("usage", d)
        out.append({
            "node": os.path.splitext(os.path.basename(path))[0],
            "model": d.get("model", "?"),
            "input": u.get("input_tokens", 0),
            "output": u.get("output_tokens", 0),
            "cache_read": u.get("cache_read_input_tokens", 0),
            "cost_usd": d.get("total_cost_usd"),
        })
    return out


def cmd_record(argv: list[str]) -> int:
    run = argv[0]
    rec_path = os.path.join(RUNS, f"{run}.json")
    record = {}
    if os.path.exists(rec_path):
        with open(rec_path, encoding="utf-8") as fh:
            record = json.load(fh)
    nodes = node_usage(run)
    record["nodes"] = nodes
    record["tokens"] = {
        "input": sum(n["input"] for n in nodes),
        "output": sum(n["output"] for n in nodes),
        "cache_read": sum(n["cache_read"] for n in nodes),
    }
    costs = [n["cost_usd"] for n in nodes if isinstance(n["cost_usd"], (int, float))]
    #  Reported only when every node reported one. A partial total reads as a full total
    #  and is the number somebody will quote later.
    record["cost_usd"] = round(sum(costs), 4) if len(costs) == len(nodes) and nodes else None
    record["cost_complete"] = bool(nodes) and len(costs) == len(nodes)
    os.makedirs(RUNS, exist_ok=True)
    with open(rec_path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)
    t = record["tokens"]
    print(f"COST_RECORDED run={run} nodes={len(nodes)} "
          f"in={t['input']} out={t['output']} cached={t['cache_read']} "
          f"usd={record['cost_usd'] if record['cost_complete'] else 'incomplete'}")
    return 0


def cmd_report(_argv: list[str]) -> int:
    runs = sorted(glob.glob(os.path.join(RUNS, "*.json")))
    total_in = total_out = 0
    per_node: dict[str, dict] = {}
    counted = 0
    print(f"{'run':<20} {'nodes':>5} {'input':>10} {'output':>9} {'usd':>8}")
    for path in runs:
        if os.path.basename(path) == "last.json":
            continue
        with open(path, encoding="utf-8") as fh:
            r = json.load(fh)
        t = r.get("tokens")
        if not t:
            continue
        counted += 1
        total_in += t["input"]
        total_out += t["output"]
        usd = r.get("cost_usd")
        print(f"{r.get('run','?'):<20} {len(r.get('nodes',[])):>5} "
              f"{t['input']:>10,} {t['output']:>9,} "
              f"{(f'{usd:.2f}' if usd is not None else '  --'):>8}")
        for n in r.get("nodes", []):
            d = per_node.setdefault(n["node"], {"input": 0, "output": 0, "runs": 0})
            d["input"] += n["input"]
            d["output"] += n["output"]
            d["runs"] += 1

    print(f"\nRUNS_COUNTED={counted}")
    if not counted:
        print("No instrumented runs yet. This is a report of nothing, not a report of "
              "zero cost.")
        return 0
    print(f"TOTAL input={total_in:,} output={total_out:,}")
    print("\nper node, averaged across runs:")
    for name, d in sorted(per_node.items(), key=lambda kv: -kv[1]["output"]):
        print(f"  {name:<12} runs={d['runs']:<3} "
              f"avg_in={d['input'] // d['runs']:>9,} "
              f"avg_out={d['output'] // d['runs']:>8,}")
    print("\nThe plan node should dominate output tokens and cost. If it does not, the "
          "premium model is in the wrong slot (FACTORY_RULES.md 8).")
    return 0


COMMANDS = {"record": cmd_record, "report": cmd_report}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(2)
    sys.exit(COMMANDS[sys.argv[1]](sys.argv[2:]))
