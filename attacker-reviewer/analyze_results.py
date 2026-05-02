#!/usr/bin/env python3
"""Analyze attacker-reviewer ablation results against BugBot baselines.

Reads JSONL result files and chains.db BugBot data, produces comparison tables.

Usage:
    python attacker-reviewer/analyze_results.py
"""

import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
RESULTS_DIR = Path(__file__).resolve().parent / "results"
CHAINS_DB = PROJECT / "benchmark" / "chain_testing" / "chains.db"
XLSX = PROJECT / "research" / "v2_final.xlsx"


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().strip().splitlines() if l.strip()]


def load_bugbot_stage3() -> dict[str, dict]:
    """Load BugBot stage3_only results from chains.db trials table.

    Returns an empty dict if the database is missing or doesn't yet have
    a `trials` table — typical for a fresh public clone.
    """
    if not CHAINS_DB.exists():
        return {}
    conn = sqlite3.connect(str(CHAINS_DB))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT chain_id, model, verdict FROM trials WHERE diff_mode = 'stage3_only'"
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    finally:
        conn.close()

    by_chain: dict[str, dict] = defaultdict(dict)
    for r in rows:
        by_chain[r["chain_id"]][r["model"]] = r["verdict"]
    return dict(by_chain)


def load_bugbot_cumulative() -> dict[str, dict]:
    """Load BugBot cumulative results from v2_final.xlsx."""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(str(XLSX), data_only=True)
        ws = wb.active
        result = {}
        for row in ws.iter_rows(min_row=2, values_only=True):
            cid = row[0]
            if not cid:
                continue
            result[cid] = {
                "bb_opus": str(row[9] or "").upper().strip(),
                "bb_sonnet": str(row[10] or "").upper().strip(),
                "bb_codex": str(row[11] or "").upper().strip(),
                "tier": row[13],
            }
        return result
    except Exception as e:
        print(f"Warning: Could not load xlsx: {e}")
        return {}


def analyze_experiment(name: str, results: list[dict]) -> dict:
    """Compute stats for a single experiment."""
    verdicts = Counter(e["attacker_verdict"] for e in results)
    total = verdicts["DECLINE"] + verdicts["APPROVE"]
    return {
        "name": name,
        "total": total,
        "decline": verdicts["DECLINE"],
        "approve": verdicts["APPROVE"],
        "error": verdicts.get("ERROR", 0),
        "rate": verdicts["DECLINE"] / total if total else 0,
    }


def main():
    # Load all experiment results
    experiments = {}
    for f in sorted(RESULTS_DIR.glob("*.jsonl")):
        name = f.stem
        data = load_jsonl(f)
        if data:
            experiments[name] = data

    if not experiments:
        print("No results found in", RESULTS_DIR)
        return

    # Load baselines
    bb_cumulative = load_bugbot_cumulative()
    bb_stage3 = load_bugbot_stage3()

    # ===== Overall comparison table =====
    print("=" * 80)
    print("ATTACKER-REVIEWER EXPERIMENT RESULTS")
    print("=" * 80)

    print("\n--- Gemma 4B Experiments ---")
    print(f"{'Experiment':<35} {'Tested':>7} {'DECLINE':>8} {'APPROVE':>8} {'Rate':>7}")
    print("-" * 70)
    for name, data in sorted(experiments.items()):
        s = analyze_experiment(name, data)
        print(f"{s['name']:<35} {s['total']:>7} {s['decline']:>8} {s['approve']:>8} {s['rate']:>6.0%}")

    # ===== BugBot baselines =====
    print("\n--- BugBot Baselines (from chains.db + v2_final.xlsx) ---")

    # Cumulative
    if bb_cumulative:
        for model in ["bb_opus", "bb_sonnet", "bb_codex"]:
            vals = [v[model] for v in bb_cumulative.values() if v[model] in ("APPROVE", "DECLINE")]
            decl = sum(1 for v in vals if v == "DECLINE")
            total = len(vals)
            if total:
                print(f"  BugBot {model:<12} cumulative:  {decl}/{total} DECLINE ({100*decl/total:.0f}%)")

    # Stage3
    if bb_stage3:
        for model in ["codex", "opus", "sonnet", "gemini"]:
            vals = [v.get(model, "") for v in bb_stage3.values()]
            vals = [v for v in vals if v in ("APPROVE", "DECLINE")]
            decl = sum(1 for v in vals if v == "DECLINE")
            total = len(vals)
            if total:
                print(f"  BugBot {model:<12} stage3_only: {decl}/{total} DECLINE ({100*decl/total:.0f}%)")

    # ===== Head-to-head: pentester stage3 vs BugBot stage3 =====
    if "pentester_stage3" in experiments and bb_stage3:
        print("\n--- HEAD-TO-HEAD: Gemma pentester vs BugBot (stage3_only) ---")
        gemma_s3 = {e["chain_id"]: e["attacker_verdict"] for e in experiments["pentester_stage3"]}

        # Find overlap
        overlap_chains = set(gemma_s3.keys()) & set(bb_stage3.keys())
        print(f"  Overlap chains: {len(overlap_chains)}")

        for bb_model in ["codex", "opus", "sonnet"]:
            both_tested = 0
            gemma_catches = 0
            bb_catches = 0
            both_catch = 0
            neither = 0
            gemma_only = 0
            bb_only = 0

            for cid in overlap_chains:
                gv = gemma_s3.get(cid, "")
                bv = bb_stage3[cid].get(bb_model, "")
                if gv not in ("APPROVE", "DECLINE") or bv not in ("APPROVE", "DECLINE"):
                    continue
                both_tested += 1
                gc = gv == "DECLINE"
                bc = bv == "DECLINE"
                if gc and bc: both_catch += 1
                elif gc and not bc: gemma_only += 1
                elif not gc and bc: bb_only += 1
                else: neither += 1

            if both_tested:
                print(f"\n  vs BB {bb_model} (n={both_tested}):")
                print(f"    Both catch:    {both_catch:3d} ({100*both_catch/both_tested:.0f}%)")
                print(f"    Gemma only:    {gemma_only:3d} ({100*gemma_only/both_tested:.0f}%)")
                print(f"    BB only:       {bb_only:3d} ({100*bb_only/both_tested:.0f}%)")
                print(f"    Neither:       {neither:3d} ({100*neither/both_tested:.0f}%)")

    # ===== Prompt ablation =====
    if "pentester_full" in experiments and "original_cumulative" in experiments:
        print("\n--- PROMPT ABLATION: pentester vs original (Gemma 4B, cumulative) ---")
        pent = {e["chain_id"]: e["attacker_verdict"] for e in experiments["pentester_full"]}
        orig = {e["chain_id"]: e["attacker_verdict"] for e in experiments["original_cumulative"]}
        overlap = set(pent.keys()) & set(orig.keys())
        overlap = [c for c in overlap if pent[c] in ("APPROVE","DECLINE") and orig[c] in ("APPROVE","DECLINE")]
        print(f"  Overlap: {len(overlap)} chains")

        both_d = sum(1 for c in overlap if pent[c] == "DECLINE" and orig[c] == "DECLINE")
        pent_only = sum(1 for c in overlap if pent[c] == "DECLINE" and orig[c] == "APPROVE")
        orig_only = sum(1 for c in overlap if pent[c] == "APPROVE" and orig[c] == "DECLINE")
        neither = sum(1 for c in overlap if pent[c] == "APPROVE" and orig[c] == "APPROVE")
        print(f"  Both DECLINE:      {both_d}")
        print(f"  Pentester only:    {pent_only}")
        print(f"  Original only:     {orig_only}")
        print(f"  Both APPROVE:      {neither}")


if __name__ == "__main__":
    main()
