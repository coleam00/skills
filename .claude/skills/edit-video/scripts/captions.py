"""Caption phrases on the output timeline.

Usage: uv run --project $S python captions.py <ws> [--tag v1]
Input : cut/words_<tag>.json (validate_cut.py) and optional <ws>/caption_fixes.json:
        {"Cloud Code": "Claude Code", "11am": "11 AM", "_keep": ["Save My Seat"]}
        Fixes match the words as PRINTED by this script (after "hands" + "-on" are glued), case and punctuation
        insensitive, and may add punctuation ("hello there" -> "Hello there."). "_keep" phrases never split across two
        captions. Captions show what was SAID, never a script the speaker paraphrased.
Output: cut/captions_<tag>.json {"words": [...], "groups": [{text, s, e, words: [idx]}]}
Grouping: split at punctuation, pauses > 0.25 s and segment joins; balance each clause into near-equal phrases
(<= MAX chars); merge anything spoken in < 0.5 s into a neighbour so nothing flashes.
"""
import json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import load, save, ws

def balanced(idx, words, target, hard, nobreak=frozenset()):
    """Split a clause into near-equal phrases. nobreak: word indices that must stay with the word after them."""
    L = lambda a, b: len(" ".join(words[j]["w"] for j in idx[a:b])); n = len(idx)
    k = max(1, -(-L(0, n) // target))
    while True:
        mean = L(0, n) / k; best = {(0, 0): (0.0, [])}
        for parts in range(1, k + 1):
            for end in range(1, n + 1):
                c = [(best[(parts - 1, st)][0] + (L(st, end) - mean) ** 2, best[(parts - 1, st)][1] + [(st, end)])
                     for st in range(end) if (parts - 1, st) in best and (L(st, end) <= hard or end - st == 1)
                     and not (end < n and idx[end - 1] in nobreak)]
                if c: best[(parts, end)] = min(c)
        if (k, n) in best: return [idx[a:b] for a, b in best[(k, n)][1]]
        k += 1

def main():
    d, cfg = ws(); tag = sys.argv[sys.argv.index("--tag") + 1] if "--tag" in sys.argv else "v1"
    words = load(d, "cut", f"words_{tag}.json")
    if not words: sys.exit("Run validate_cut.py first (it writes cut/words_<tag>.json)")
    # Whisper splits "hands-on" / "11 a.m." into fragments ("-on", ".m."): glue them back onto the previous word
    merged = []
    for w in words:
        if merged and (w["w"][:1] in "-." or w["w"] in ("'s",)) and w["seg"] == merged[-1]["seg"]:
            merged[-1]["w"] += w["w"]; merged[-1]["e"] = w["e"]
        else: merged.append(dict(w))
    words = merged
    # house style: pronoun I, AI, sentence-initial capitals (Whisper sometimes returns a lower-cased take)
    for i, w in enumerate(words):
        core = re.sub(r"[^a-z']", "", w["w"].lower())
        if core in ("i", "i'm", "i'll", "i've", "i'd"): w["w"] = "I" + w["w"][1:]
        if core in ("ai",): w["w"] = w["w"].replace("ai", "AI")
        if (i == 0 or words[i - 1]["w"][-1:] in ".?!" or words[i - 1]["seg"] != w["seg"]) and w["w"][:1].isalpha():
            w["w"] = w["w"][0].upper() + w["w"][1:]
    # caption_fixes: match on words (punctuation-insensitive), replace the span, spread its time over the new words
    key = lambda s: re.sub(r"[^a-z0-9']", "", s.lower())
    fx = load(d, "caption_fixes.json", default={}) or {}; keep = fx.pop("_keep", [])
    for a, b in fx.items():
        A, B = [key(t) for t in a.split()], b.split(); i = 0; hits = 0
        while i <= len(words) - len(A):
            if [key(w["w"]) for w in words[i:i + len(A)]] == A:
                span = words[i:i + len(A)]; tail = re.sub(r"^.*?([.,?!:;]*)$", r"\1", span[-1]["w"])
                s0, e0, dt = span[0]["s"], span[-1]["e"], (span[-1]["e"] - span[0]["s"]) / len(B)
                new = [{"w": t, "s": round(s0 + k * dt, 3), "e": round(s0 + (k + 1) * dt, 3), "seg": span[0]["seg"]} for k, t in enumerate(B)]
                new[-1]["w"] += tail if not new[-1]["w"].endswith(tail) else ""; new[-1]["e"] = e0
                words[i:i + len(A)] = new; i += len(B); hits += 1
            else: i += 1
        if not hits: print(f"WARN caption fix {a!r} matched nothing")
    vertical = cfg["h"] > cfg["w"]
    target, hard = (22, 26) if vertical else (34, 42)
    merge_max = hard + (2 if vertical else 5)   # a merged phrase must still fit one line: 31 chars wrapped at 1080 wide
    nobreak = set()
    for ph in keep:
        K = [key(t) for t in ph.split()]; hit = False
        for i in range(len(words) - len(K) + 1):
            if [key(w["w"]) for w in words[i:i + len(K)]] == K: nobreak.update(range(i, i + len(K) - 1)); hit = True
        if not hit: print(f"WARN _keep {ph!r} matched nothing")
    clauses, cur = [], []
    for i, w in enumerate(words):
        cur.append(i); nx = words[i + 1] if i + 1 < len(words) else None
        if nx is None or ((w["w"][-1] in ".,?!:;" or nx["s"] - w["e"] > 0.25) and i not in nobreak) or nx["seg"] != w["seg"]:
            clauses.append(cur); cur = []
    groups = [g for c in clauses for g in balanced(c, words, target, hard, nobreak)]
    txt = lambda g: " ".join(words[j]["w"] for j in g)
    changed = True
    while changed:
        changed = False
        for i, g in enumerate(groups):
            # time ON SCREEN, not time spoken: a phrase ends where the next one starts (overlapping word stamps)
            nxt_s = words[groups[i + 1][0]]["s"] if i + 1 < len(groups) else 1e9
            if min(nxt_s, words[g[-1]]["e"] + 0.6) - words[g[0]]["s"] >= 0.5: continue
            opts = []
            if i + 1 < len(groups) and words[groups[i + 1][0]]["seg"] == words[g[0]]["seg"] and len(txt(g + groups[i + 1])) <= merge_max and words[g[-1]]["w"][-1] not in ".?!":
                opts.append((len(txt(g + groups[i + 1])), i, i + 1))
            if i > 0 and words[groups[i - 1][0]]["seg"] == words[g[0]]["seg"] and len(txt(groups[i - 1] + g)) <= merge_max and words[groups[i - 1][-1]]["w"][-1] not in ".?!":
                opts.append((len(txt(groups[i - 1] + g)), i - 1, i))
            if opts:
                _, a, b = min(opts); groups[a:b + 1] = [groups[a] + groups[b]]; changed = True; break
            # too long to merge whole: borrow the next phrase's first word instead ("and the thing that" + "always"),
            # with any _keep words chained to it ("Thanks to" + "Acme Systems")
            if i + 1 < len(groups) and words[groups[i + 1][0]]["seg"] == words[g[0]]["seg"] and words[g[-1]]["w"][-1] not in ".?!":
                nx_ = groups[i + 1]; j = 1
                while j < len(nx_) and nx_[j - 1] in nobreak: j += 1
                if j < len(nx_) and len(txt(g + nx_[:j])) <= merge_max:
                    groups[i] = g + nx_[:j]; groups[i + 1] = nx_[j:]; changed = True; break
    out = [{"text": txt(g), "s": words[g[0]]["s"], "e": words[g[-1]]["e"], "words": g} for g in groups]
    for a, b in zip(out, out[1:]): a["e"] = round(min(b["s"], a["e"] + 0.6), 3)
    out[-1]["e"] = round(out[-1]["e"] + 0.4, 3)
    save({"words": words, "groups": out}, d, "cut", f"captions_{tag}.json")
    print(f"{len(words)} words -> {len(out)} phrases (max {max(len(g['text']) for g in out)} chars)")
    for g in out: print(f"  {g['s']:7.2f}  {g['text']}" + ("   SHORT (< 0.5 s on screen)" if g["e"] - g["s"] < 0.5 else ""))

if __name__ == "__main__":
    main()
