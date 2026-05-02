# Attacker-Reviewer Defense

Exploit-oriented code review using a small open model (Gemma 4 E4B, 4B params) with adversarial **pentester** prompting. The framing — *"write an exploit"* rather than *"check if safe"* — shifts the defense Pareto frontier far more than model scale does.

## Headline numbers

| Defense | Cost / PR | Detection | Diamonds (n=21) | FP on benign PRs |
|---|---|---|---|---|
| Semgrep | $0 | 0% | 0% | ~0% |
| **Gemma pentester** | **~$0.01** | **90.1%** | **~95%** | **5.3%** (Wilson 95% CI 3.7–7.5%) |
| BugBot Opus 4.6 | ~$15 | 62% | 0% | n/a |

**5.3% raw FP** measured on **608** sampled benign PRs from 8 popular open-source repos (533 valid verdicts; 75 ERROR). Diamonds = chains that evade *all four* production diff-mode BugBot reviewers.

## 2×2 ablation (same 4B model, four prompts)

|  | Cumulative diff | Stage-3 only | Δ Context |
|---|---|---|---|
| Pentester prompt | **90.1%** | **72.8%** | +17 pp |
| Original / neutral | 23.1% | 24.8% | −2 pp |
| **Δ Prompt** | **+67 pp** | **+48 pp** | |

Prompt framing (+67 pp) dominates diff context (+17 pp) by ~3×. The neutral prompt is barely above chance; the pentester prompt is the entire effect.

## What's in this directory

| File | Purpose |
|---|---|
| `prompts/{original,paranoid,hostile,pentester}.txt` | The four prompt variants used in the ablation |
| `results/pentester_full.jsonl` | 90.1% on 131 chains × cumulative diff |
| `results/pentester_stage3.jsonl` | 72.8% on stage-3-only |
| `results/original_cumulative.jsonl` | 23.1% baseline (cumulative) |
| `results/original_stage3.jsonl` | 24.8% baseline (stage-3-only) |
| `results/benign_fp_500.jsonl` | 608-PR FP audit |
| `analyze_results.py` | Aggregator — recomputes the ablation tables and FP CIs |
| `ablation_results.md` | Pre-rendered tables + paper implication |

## Reproducing the numbers

```bash
python analyze_results.py
```

Re-runs the four ablation cells (pentester / original × cumulative / stage-3) and the 608-PR FP audit from the JSONL files in `results/`, and prints the tables above plus Wilson 95% CIs.

To re-score chains end-to-end with the pentester prompt, the harness wires this defense in as `attacker_reviewer` (see `mosaic/defense.py` and `mosaic/attacker_reviewer.py`). The model itself is served via Vertex AI Model Garden (Gemma 4 E4B). Set `MOSAIC_ATTACKER_BACKEND`, `MOSAIC_ATTACKER_PROMPT`, and `MOSAIC_ATTACKER_VERTEX_ENDPOINT_ID` per the top-level [`README.md`](../README.md#environment-variables).
