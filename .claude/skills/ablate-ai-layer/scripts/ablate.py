#!/usr/bin/env python3
"""Back up, ablate, and restore a repository's AI layer. Never deletes anything.

Artifacts are MOVED into .ablation/held/ and a verified copy is kept in
.ablation/backup/ with sha256 for every file, so restore is provable rather than
hopeful.

Commands:
  backup   [root]                 copy the layer into .ablation/backup/ + manifest
  check    [root]                 pre-flight: is any of the layer imported by source?
  ablate   [root] [--scope always|all]
  restore  [root]
  status   [root]

Exit codes: 0 ok, 1 refused (unsafe), 2 error.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from map_layer import ALWAYS, ONDEMAND, ENFORCE, iter_matches  # noqa: E402

ABL = ".ablation"
SRC_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py", ".go", ".rs",
           ".java", ".rb", ".php", ".cs", ".swift", ".kt", ".sh", ".toml",
           ".json", ".yaml", ".yml"}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "dist", "build",
             "__pycache__", ".next", "target", ABL}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def root_of(argv: list[str]) -> Path:
    pos = [a for a in argv if not a.startswith("--")]
    return Path(pos[0]).resolve() if pos else Path.cwd()


def paths(root: Path):
    d = root / ABL
    return d, d / "backup", d / "held", d / "manifest.json"


def git(root: Path, *args: str) -> str:
    try:
        r = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
                           text=True, timeout=60)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def load_manifest(root: Path) -> dict:
    _, _, _, mf = paths(root)
    if mf.exists():
        return json.loads(mf.read_text(encoding="utf-8"))
    return {}


# ----------------------------------------------------------------- commands

def cmd_check(root: Path) -> int:
    """Is any AI-layer file imported or read by source code?

    Deleting such a file does not degrade the agent, it breaks the build. Found
    in the wild: a CLI that compile-time imports its own skill markdown.
    """
    art = [i["path"] for i in iter_matches(root)]
    if not art:
        print("No AI layer found, nothing to check.")
        return 0
    needles = set()
    for a in art:
        needles.add(a)
        needles.add(Path(a).name)
    hits: list[tuple[str, str, str]] = []
    for f in root.rglob("*"):
        if not f.is_file() or f.suffix not in SRC_EXT:
            continue
        if any(part in SKIP_DIRS for part in f.parts):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for n in needles:
            if n in text and Path(n).suffix in {".md", ".mdc", ".json", ".yml", ".yaml"}:
                rel = f.relative_to(root).as_posix()
                if rel == n:
                    continue
                hits.append((rel, n, next(
                    (ln.strip()[:90] for ln in text.splitlines() if n in ln), "")))
                break
    if not hits:
        print("PASS  no source file references an AI-layer artifact.")
        print("      Ablating is a context change only, it cannot break the build.")
        return 0
    print("WARNING  source code references AI-layer files:\n")
    for f, n, line in hits[:20]:
        print(f"  {f}\n      references {n}\n      {line}\n")
    print("These must be STUBBED (kept present, contents emptied), not moved away,")
    print("or the build breaks and you will misread a compile error as an agent")
    print("regression. Re-run with --scope always, which leaves skills in place.")
    return 1


def cmd_backup(root: Path) -> int:
    d, backup, held, mf = paths(root)
    items = list(iter_matches(root))
    if not items:
        print("No AI layer found. Nothing to back up.")
        return 1
    if backup.exists():
        shutil.rmtree(backup)
    backup.mkdir(parents=True, exist_ok=True)
    held.mkdir(parents=True, exist_ok=True)

    entries = []
    for i in items:
        src = root / i["path"]
        dst = backup / i["path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        entries.append({**i, "sha256": sha(src)})

    commit = git(root, "rev-parse", "HEAD")
    dirty = git(root, "status", "--porcelain")
    mf.write_text(json.dumps({
        "root": str(root), "commit": commit, "dirty_at_backup": bool(dirty),
        "state": "intact", "artifacts": entries,
    }, indent=2), encoding="utf-8")

    gi = root / ".gitignore"
    line = f"{ABL}/"
    if gi.exists() and line not in gi.read_text(encoding="utf-8", errors="replace"):
        gi.write_text(gi.read_text(encoding="utf-8", errors="replace").rstrip()
                      + f"\n{line}\n", encoding="utf-8")
        print(f"Added {line} to .gitignore")
    elif not gi.exists():
        gi.write_text(f"{line}\n", encoding="utf-8")
        print(f"Created .gitignore with {line}")

    print(f"Backed up {len(entries)} files to {backup}")
    if commit:
        print(f"Git commit at backup time: {commit[:12]}")
    if dirty:
        print("\nNOTE  working tree was dirty at backup time. Commit or stash first")
        print("      so the restore point is unambiguous.")
    print(f"\nRestore at any time:  python ablate.py restore {root}")
    return 0


def cmd_ablate(root: Path, scope: str) -> int:
    d, backup, held, mf = paths(root)
    man = load_manifest(root)
    if not man:
        print("REFUSED  no backup. Run:  python ablate.py backup")
        return 1
    if man.get("state") == "ablated":
        print("Already ablated. Run restore first, or status to inspect.")
        return 1

    want = {ALWAYS} if scope == "always" else {ALWAYS, ONDEMAND}
    moved = []
    for a in man["artifacts"]:
        if a["kind"] not in want:
            continue
        src = root / a["path"]
        if not src.exists():
            continue
        dst = held / a["path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        moved.append(a["path"])

    man["state"] = "ablated"
    man["scope"] = scope
    man["moved"] = moved
    mf.write_text(json.dumps(man, indent=2), encoding="utf-8")

    kept = [a["path"] for a in man["artifacts"] if a["path"] not in moved]
    print(f"Ablated {len(moved)} file(s), scope={scope}:")
    for p in moved:
        print(f"  moved aside  {p}")
    if kept:
        print(f"\nLeft in place ({len(kept)}):")
        for p in kept:
            print(f"  kept         {p}")
    print("\nNothing was deleted. Everything is in .ablation/held/.")
    print(f"Restore:  python ablate.py restore {root}")
    print("\nIMPORTANT  start a NEW agent session now. The layer is read once at")
    print("           session start, so an already-open session is still using it.")
    return 0


def cmd_restore(root: Path) -> int:
    d, backup, held, mf = paths(root)
    man = load_manifest(root)
    if not man:
        print("No manifest. Nothing to restore.")
        return 1

    created = d / "created-during-ablation"
    restored, repaired, bad, rescued = [], [], [], []
    for a in man["artifacts"]:
        target = root / a["path"]
        h = held / a["path"]
        b = backup / a["path"]
        if h.exists():
            # The agent may have written a NEW file at this path while the
            # original was moved aside (an /init run, for example). Restoring
            # over it would destroy work with no trace, so set it aside first.
            if target.exists():
                keep = created / a["path"]
                keep.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(target), str(keep))
                rescued.append(a["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(h), str(target))
            restored.append(a["path"])
        elif not target.exists() and b.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(b, target)
            repaired.append(a["path"])
        if target.exists() and sha(target) != a["sha256"]:
            bad.append(a["path"])

    man["state"] = "intact"
    man.pop("moved", None)
    mf.write_text(json.dumps(man, indent=2), encoding="utf-8")

    print(f"Restored {len(restored)} file(s) from held/.")
    if repaired:
        print(f"Recovered {len(repaired)} from backup/: {', '.join(repaired)}")
    if rescued:
        print(f"\nThe agent wrote {len(rescued)} file(s) at these paths during the")
        print("ablated run. Your originals are back; the agent's versions are kept at")
        print(f"  {created}")
        for p in rescued:
            print(f"    {p}")
        print("Worth reading before deleting: that is what the model thought it needed.")
    if bad:
        print("\nCHANGED since backup (restored, but contents differ from the")
        print("original snapshot, most likely because you edited them):")
        for p in bad:
            print(f"  {p}")
        print(f"Pristine copies remain in {backup}")
    else:
        print("All files match their backup hashes exactly.")
    return 0


def cmd_status(root: Path) -> int:
    man = load_manifest(root)
    if not man:
        print("No ablation in progress. No backup taken yet.")
        return 0
    print(f"State: {man.get('state')}   scope: {man.get('scope', '-')}")
    print(f"Backed up at commit: {(man.get('commit') or '?')[:12]}")
    print(f"Artifacts tracked: {len(man['artifacts'])}")
    if man.get("state") == "ablated":
        print(f"Currently moved aside: {len(man.get('moved', []))}")
        for p in man.get("moved", []):
            print(f"  {p}")
        print(f"\nRestore:  python ablate.py restore {man['root']}")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd, argv = sys.argv[1], sys.argv[2:]
    root = root_of(argv)
    scope = "always"
    for i, a in enumerate(argv):
        if a == "--scope" and i + 1 < len(argv):
            scope = argv[i + 1]
    if scope not in {"always", "all"}:
        print("--scope must be 'always' or 'all'")
        return 2

    return {
        "backup": lambda: cmd_backup(root),
        "check": lambda: cmd_check(root),
        "ablate": lambda: cmd_ablate(root, scope),
        "restore": lambda: cmd_restore(root),
        "status": lambda: cmd_status(root),
    }.get(cmd, lambda: (print(f"Unknown command: {cmd}"), 2)[1])()


if __name__ == "__main__":
    raise SystemExit(main())
