"""Build a reader-friendly walkthrough of every score that goes into RQ4.

Reads `data/processed/agreement_stats.json` (which `compute_agreement.py`
emits) and writes two assets:

  assets/rq4_walkthrough.csv  — flat one-row-per-quantity CSV for analysis
  assets/rq4_walkthrough.md   — sectioned markdown that mirrors the
                                manuscript's RQ4 prose, step by step

Use this to verify the numbers the manuscript prints against the JSON,
and to re-derive each step (cohort → per-condition mean → cluster CI →
paired Δ → TOST → blind-human cross-check → judge–human gap) without
re-reading the entire RQ4 section.

  python scripts/rq4_walkthrough_table.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
PROCESSED = HERE / "data" / "processed"
ASSETS = HERE / "assets"


def _fmt(v, w=2):
    return "—" if v is None else f"{v:+.{w}f}" if isinstance(v, float) and abs(v) < 100 else f"{v:.{w}f}"


def _f(v, w=2):
    return "—" if v is None else f"{v:.{w}f}"


def _gp(raw_points):
    """Convert a raw 0-100 difference to grade points on 0-18 scale."""
    return None if raw_points is None else raw_points * 18 / 100


def main():
    ag = json.loads((PROCESSED / "agreement_stats.json").read_text())
    r4 = ag.get("rq4_cocreation") or {}
    r4b = ag.get("rq4_cocreation_by_bereich") or {}
    r4h = ag.get("rq4_cocreation_blind_human") or {}
    r4_tost = ag.get("rq4_cocreation_vs_flagship_tost") or {}
    tier = ag.get("tier_aggregates") or {}
    flagship = ((tier.get("benchathon") or {}).get("by_tier") or {}).get("flagship") or {}

    # --------------- CSV: flat one-row-per-quantity ---------------
    rows = []
    def add(step, quantity, value, ci_lo=None, ci_hi=None, n=None, note=""):
        rows.append({
            "step": step,
            "quantity": quantity,
            "value": value,
            "ci95_lo": ci_lo,
            "ci95_hi": ci_hi,
            "n": n,
            "note": note,
        })

    # Step 1 — cohort and per-condition pools
    add("1.cohort", "n_annotations_traditional",
        r4.get("n_traditional"), n=r4.get("n_traditional"),
        note="judge-based RQ4 pool")
    add("1.cohort", "n_annotations_co_creation",
        r4.get("n_co_creation"), n=r4.get("n_co_creation"))
    add("1.cohort", "n_participants_traditional",
        r4.get("n_participants_trad"),
        note="participants who contributed >=1 trad annotation")
    add("1.cohort", "n_participants_co_creation",
        r4.get("n_participants_ai"))
    add("1.cohort", "n_participants_paired_both_arms",
        r4.get("n_participants_paired"),
        note="participants who contributed to both arms")
    add("1.cohort", "n_participants_co_creation_only",
        (r4.get("n_participants_ai") or 0) - (r4.get("n_participants_paired") or 0),
        note="the 10 less-experienced participants who skipped trad")

    # Step 2 — mean scores per condition (judge-based)
    add("2.means", "mean_judge_raw_traditional", r4.get("mean_traditional"),
        n=r4.get("n_traditional"), note="LLM-judge raw 0-100")
    add("2.means", "mean_judge_raw_co_creation", r4.get("mean_co_creation"),
        n=r4.get("n_co_creation"))

    # Step 3 — mean difference under multiple resampling units
    add("3.delta.iid", "mean_diff_ai_minus_trad",
        r4.get("mean_diff_ai_minus_trad_iid"),
        ci_lo=r4.get("ci95_lo_iid"), ci_hi=r4.get("ci95_hi_iid"),
        n=(r4.get("n_traditional") or 0) + (r4.get("n_co_creation") or 0),
        note="i.i.d. annotation bootstrap (diagnostic; assumes annotations independent)")
    add("3.delta.cluster_participant", "mean_diff_ai_minus_trad",
        r4.get("mean_diff_ai_minus_trad"),
        ci_lo=r4.get("ci95_lo"), ci_hi=r4.get("ci95_hi"),
        n=(r4.get("n_participants_trad") or 0) + (r4.get("n_participants_ai") or 0),
        note="HEADLINE: participant-cluster bootstrap (resamples participants)")
    add("3.delta.cluster_task", "mean_diff_ai_minus_trad",
        r4.get("mean_diff_cluster_task"),
        ci_lo=r4.get("ci95_lo_cluster_task"), ci_hi=r4.get("ci95_hi_cluster_task"),
        n=15,
        note="task-cluster bootstrap (resamples Benchathon tasks)")
    add("3.delta.paired_within_participant", "mean_diff_ai_minus_trad",
        r4.get("mean_diff_paired_within_participant"),
        ci_lo=r4.get("ci95_lo_paired_within_participant"),
        ci_hi=r4.get("ci95_hi_paired_within_participant"),
        n=r4.get("n_participants_paired"),
        note="within-participant paired delta (n=participants in both arms)")
    add("3.delta.grade_points", "mean_diff_ai_minus_trad_grade_points",
        _gp(r4.get("mean_diff_ai_minus_trad")),
        ci_lo=_gp(r4.get("ci95_lo")), ci_hi=_gp(r4.get("ci95_hi")),
        note="headline delta converted to 0-18 grade-points scale")

    # Step 4 — by Bereich (descriptive only, no inferential domain test)
    for bereich, b in (r4b or {}).items():
        if not b:
            continue
        add(f"4.bereich.{bereich}", "mean_traditional", b.get("mean_traditional"),
            n=b.get("n_traditional"))
        add(f"4.bereich.{bereich}", "mean_co_creation", b.get("mean_co_creation"),
            n=b.get("n_co_creation"))
        add(f"4.bereich.{bereich}", "mean_diff_ai_minus_trad",
            b.get("mean_diff_ai_minus_trad"),
            ci_lo=b.get("ci95_lo"), ci_hi=b.get("ci95_hi"),
            note="i.i.d. bootstrap, descriptive only")

    # Step 5 — TOST vs flagship tier
    add("5.tost", "co_creation_mean", r4.get("mean_co_creation"))
    add("5.tost", "flagship_tier_mean", flagship.get("mean_raw"),
        ci_lo=flagship.get("ci95_lo"), ci_hi=flagship.get("ci95_hi"),
        note="per-generation i.i.d. bootstrap on flagship pool")
    add("5.tost", "delta_co_creation_minus_flagship",
        r4_tost.get("point_estimate"))
    add("5.tost", "tost_eq_band_lo", r4_tost.get("eq_low"),
        note="equivalence band lower edge (raw points)")
    add("5.tost", "tost_eq_band_hi", r4_tost.get("eq_high"))
    add("5.tost", "tost_one_sided_95_lower",
        r4_tost.get("one_sided_lower_95"),
        note="reject Δ <= eq_low iff this > eq_low")
    add("5.tost", "tost_one_sided_95_upper",
        r4_tost.get("one_sided_upper_95"),
        note="reject Δ >= eq_high iff this < eq_high")
    add("5.tost", "tost_reject_h0_low",
        r4_tost.get("reject_h0_low"))
    add("5.tost", "tost_reject_h0_high",
        r4_tost.get("reject_h0_high"))
    add("5.tost", "tost_equivalent_within_band",
        r4_tost.get("equivalent"),
        note="True iff both rejections fire")

    # Step 6 — blind-human cross-check on RQ5 validation subset
    add("6.blind_human", "n_traditional", r4h.get("n_traditional"))
    add("6.blind_human", "n_co_creation", r4h.get("n_co_creation"))
    add("6.blind_human", "n_participants_trad", r4h.get("n_participants_trad"))
    add("6.blind_human", "n_participants_ai", r4h.get("n_participants_ai"))
    add("6.blind_human", "mean_traditional", r4h.get("mean_traditional"))
    add("6.blind_human", "mean_co_creation", r4h.get("mean_co_creation"))
    add("6.blind_human", "mean_diff_ai_minus_trad",
        r4h.get("mean_diff_ai_minus_trad"),
        ci_lo=r4h.get("ci95_lo"), ci_hi=r4h.get("ci95_hi"),
        note="HEADLINE: participant-cluster bootstrap; CI spans zero at this n")
    add("6.blind_human", "mean_diff_iid_diagnostic",
        r4h.get("mean_diff_ai_minus_trad_iid"),
        ci_lo=r4h.get("ci95_lo_iid"), ci_hi=r4h.get("ci95_hi_iid"),
        note="i.i.d. bootstrap, diagnostic only")

    # Step 7 — judge vs blind-human gap on this exact contrast
    judge_delta = r4.get("mean_diff_ai_minus_trad")
    human_delta = r4h.get("mean_diff_ai_minus_trad")
    add("7.judge_vs_human_gap", "judge_delta",
        judge_delta, note="from step 3 (participant cluster)")
    add("7.judge_vs_human_gap", "blind_human_delta",
        human_delta, note="from step 6")
    add("7.judge_vs_human_gap", "gap_judge_minus_human",
        (judge_delta - human_delta) if (judge_delta is not None and human_delta is not None) else None,
        note="empirical bound on judge-style premium on this contrast")

    # ---- write CSV ----
    ASSETS.mkdir(parents=True, exist_ok=True)
    out_csv = ASSETS / "rq4_walkthrough.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["step", "quantity", "value",
                                          "ci95_lo", "ci95_hi", "n", "note"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"wrote {out_csv} ({len(rows)} rows)")

    # ---- write markdown (sectioned, manuscript-aligned) ----
    md = []
    md.append("# RQ4 walkthrough — every score behind the manuscript prose")
    md.append("")
    md.append("Auto-generated by `scripts/rq4_walkthrough_table.py`. ")
    md.append("Reads `data/processed/agreement_stats.json`. Re-run after any pipeline change.")
    md.append("")
    md.append("Sections mirror the manuscript's RQ4 build-up. Each table is one step.")
    md.append("")

    md.append("## Step 1 — Cohort and per-condition pools")
    md.append("")
    md.append("Two unbalances to keep in mind: more annotations in co-creation than traditional (skip mechanism),")
    md.append("and more participants in co-creation than traditional (the 10 less-experienced participants who skipped trad).")
    md.append("")
    md.append("| Quantity | Value | Note |")
    md.append("|---|---:|---|")
    md.append(f"| n annotations (traditional) | {r4.get('n_traditional')} | judge-based RQ4 pool |")
    md.append(f"| n annotations (co-creation) | {r4.get('n_co_creation')} | |")
    md.append(f"| n participants (traditional) | {r4.get('n_participants_trad')} | contributed ≥ 1 trad annotation |")
    md.append(f"| n participants (co-creation) | {r4.get('n_participants_ai')} | |")
    md.append(f"| n participants (both arms) | {r4.get('n_participants_paired')} | unit for paired analysis |")
    md.append(f"| n participants (co-creation only) | {(r4.get('n_participants_ai') or 0) - (r4.get('n_participants_paired') or 0)} | skipped trad — drives the imbalance |")
    md.append("")

    md.append("## Step 2 — Mean LLM-judge raw scores per condition")
    md.append("")
    md.append("| Condition | Mean raw (0–100) | n annotations |")
    md.append("|---|---:|---:|")
    md.append(f"| Traditional | {_f(r4.get('mean_traditional'), 1)} | {r4.get('n_traditional')} |")
    md.append(f"| Co-creation | {_f(r4.get('mean_co_creation'), 1)} | {r4.get('n_co_creation')} |")
    md.append("")

    md.append("## Step 3 — Mean difference Δ = co-creation − traditional, under four resampling units")
    md.append("")
    md.append("The headline is **participant-cluster bootstrap**. The other rows are diagnostics / robustness checks.")
    md.append("")
    md.append("| Resampling unit | Δ (raw) | 95% CI | n (resample unit) | Note |")
    md.append("|---|---:|---|---:|---|")
    md.append(f"| i.i.d. annotation | {_fmt(r4.get('mean_diff_ai_minus_trad_iid'), 1)} | "
              f"[{_fmt(r4.get('ci95_lo_iid'), 1)}, {_fmt(r4.get('ci95_hi_iid'), 1)}] | "
              f"{(r4.get('n_traditional') or 0) + (r4.get('n_co_creation') or 0)} | diagnostic; assumes annotations independent |")
    md.append(f"| **Participant cluster (headline)** | **{_fmt(r4.get('mean_diff_ai_minus_trad'), 1)}** | "
              f"**[{_fmt(r4.get('ci95_lo'), 1)}, {_fmt(r4.get('ci95_hi'), 1)}]** | "
              f"**{(r4.get('n_participants_trad') or 0) + (r4.get('n_participants_ai') or 0)}** | resamples participants with replacement |")
    md.append(f"| Task cluster | {_fmt(r4.get('mean_diff_cluster_task'), 1)} | "
              f"[{_fmt(r4.get('ci95_lo_cluster_task'), 1)}, {_fmt(r4.get('ci95_hi_cluster_task'), 1)}] | "
              f"15 | resamples Benchathon tasks |")
    md.append(f"| Paired within participant (n=23) | {_fmt(r4.get('mean_diff_paired_within_participant'), 1)} | "
              f"[{_fmt(r4.get('ci95_lo_paired_within_participant'), 1)}, {_fmt(r4.get('ci95_hi_paired_within_participant'), 1)}] | "
              f"{r4.get('n_participants_paired')} | eliminates between-participant covariates |")
    md.append("")
    md.append(f"**Grade-point equivalents (×18/100):** headline Δ ≈ {_fmt(_gp(r4.get('mean_diff_ai_minus_trad')), 1)} grade points, "
              f"CI [{_fmt(_gp(r4.get('ci95_lo')), 1)}, {_fmt(_gp(r4.get('ci95_hi')), 1)}]; "
              f"paired Δ ≈ {_fmt(_gp(r4.get('mean_diff_paired_within_participant')), 1)} grade points, "
              f"CI [{_fmt(_gp(r4.get('ci95_lo_paired_within_participant')), 1)}, {_fmt(_gp(r4.get('ci95_hi_paired_within_participant')), 1)}].")
    md.append("")

    md.append("## Step 4 — By legal area (descriptive only, not inferentially tested)")
    md.append("")
    md.append("| Bereich | Mean trad | Mean co-creation | Δ | 95% CI (i.i.d.) | n trad | n ai |")
    md.append("|---|---:|---:|---:|---|---:|---:|")
    for name in ("Zivilrecht", "Strafrecht", "Öffentliches Recht"):
        b = (r4b or {}).get(name)
        if not b:
            continue
        md.append(f"| {name} | {_f(b.get('mean_traditional'), 1)} | {_f(b.get('mean_co_creation'), 1)} | "
                  f"{_fmt(b.get('mean_diff_ai_minus_trad'), 1)} | "
                  f"[{_fmt(b.get('ci95_lo'), 1)}, {_fmt(b.get('ci95_hi'), 1)}] | "
                  f"{b.get('n_traditional')} | {b.get('n_co_creation')} |")
    md.append("")

    md.append("## Step 5 — TOST equivalence vs closed-flagship LLM tier")
    md.append("")
    md.append("Tests whether the co-creation pool is **equivalent** to flagship LLMs within a ±5-raw-point band.")
    md.append("Both one-sided tests must reject for equivalence to hold.")
    md.append("")
    md.append("| Quantity | Value |")
    md.append("|---|---:|")
    md.append(f"| Co-creation mean | {_f(r4.get('mean_co_creation'), 1)} |")
    md.append(f"| Flagship-tier mean | {_f(flagship.get('mean_raw'), 1)} (95% CI [{_f(flagship.get('ci95_lo'), 1)}, {_f(flagship.get('ci95_hi'), 1)}]) |")
    md.append(f"| Δ = co-creation − flagship | {_fmt(r4_tost.get('point_estimate'), 2)} |")
    md.append(f"| Equivalence band | [{_fmt(r4_tost.get('eq_low'), 1)}, {_fmt(r4_tost.get('eq_high'), 1)}] raw points |")
    md.append(f"| One-sided 95% lower bound on Δ | {_fmt(r4_tost.get('one_sided_lower_95'), 2)} |")
    md.append(f"| One-sided 95% upper bound on Δ | {_fmt(r4_tost.get('one_sided_upper_95'), 2)} |")
    md.append(f"| Reject Δ ≤ −5? | {r4_tost.get('reject_h0_low')} |")
    md.append(f"| Reject Δ ≥ +5? | {r4_tost.get('reject_h0_high')} |")
    md.append(f"| **Equivalent within ±5 raw points?** | **{r4_tost.get('equivalent')}** |")
    md.append("")

    md.append("## Step 6 — Blind-human cross-check on the RQ5 validation subset")
    md.append("")
    md.append("Same contrast, but scored by the blind human reviewer pool instead of the LLM judge.")
    md.append("Small n (15+15 solutions; ~10 participants per arm).")
    md.append("")
    md.append("| Quantity | Value | Note |")
    md.append("|---|---:|---|")
    md.append(f"| n solutions (traditional) | {r4h.get('n_traditional')} | |")
    md.append(f"| n solutions (co-creation) | {r4h.get('n_co_creation')} | |")
    md.append(f"| n participants (traditional) | {r4h.get('n_participants_trad')} | |")
    md.append(f"| n participants (co-creation) | {r4h.get('n_participants_ai')} | |")
    md.append(f"| Mean traditional | {_f(r4h.get('mean_traditional'), 1)} | blind-pool mean raw |")
    md.append(f"| Mean co-creation | {_f(r4h.get('mean_co_creation'), 1)} | |")
    md.append(f"| Δ (participant cluster, headline) | {_fmt(r4h.get('mean_diff_ai_minus_trad'), 1)} | "
              f"95% CI [{_fmt(r4h.get('ci95_lo'), 1)}, {_fmt(r4h.get('ci95_hi'), 1)}] — spans zero at this n |")
    md.append(f"| Δ (i.i.d., diagnostic) | {_fmt(r4h.get('mean_diff_ai_minus_trad_iid'), 1)} | "
              f"95% CI [{_fmt(r4h.get('ci95_lo_iid'), 1)}, {_fmt(r4h.get('ci95_hi_iid'), 1)}] |")
    md.append("")

    md.append("## Step 7 — Judge vs blind-human gap on this contrast")
    md.append("")
    md.append("The judge's Δ is larger than the human pool's Δ — quantified here. This is the empirical")
    md.append("bound on how much of the headline could be a judge-style premium on AI-assisted writing.")
    md.append("")
    md.append("| Quantity | Value | Source |")
    md.append("|---|---:|---|")
    md.append(f"| Judge Δ (participant cluster) | {_fmt(r4.get('mean_diff_ai_minus_trad'), 1)} | Step 3 (headline) |")
    md.append(f"| Blind-human Δ (participant cluster) | {_fmt(r4h.get('mean_diff_ai_minus_trad'), 1)} | Step 6 (headline) |")
    if judge_delta is not None and human_delta is not None:
        md.append(f"| **Gap = judge − human** | **{_fmt(judge_delta - human_delta, 1)} raw points** | empirical bound on judge-style premium |")
    md.append("")
    md.append("Cross-reference: the RQ5 calibration audit shows GPT-5-mini's direct offset is ")
    md.append("**+13.8 raw points on human-content picks** and **+24.5 on LLM-content picks**, a ")
    md.append("~10-raw-point content-dependent differential. The +6.3-point judge-vs-human gap here ")
    md.append("is consistent with co-creation solutions being treated as ~60% LLM-styled by the judge ")
    md.append("(see `Table tbl-judge-calibration`).")
    md.append("")

    out_md = ASSETS / "rq4_walkthrough.md"
    out_md.write_text("\n".join(md), encoding="utf-8")
    print(f"wrote {out_md}")


if __name__ == "__main__":
    main()
