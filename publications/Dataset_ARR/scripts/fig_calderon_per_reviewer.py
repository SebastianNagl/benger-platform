"""Forest plot of per-blind-reviewer d̄ for the Calderon §3 alt-test, one
row per (judge, reviewer) pair, with BY-FDR rejection markers and ω
annotation per judge. Reads `data/processed/calderon_per_judge.json`.

Layout:
  - Two panels side-by-side: human-authored picks (left), LLM-generated picks
    (right). Same x-axis for cross-corpus comparison.
  - Each panel: 3 judges × 5 reviewers = 15 rows.
  - Filled dot = BY-FDR rejected at q=0.05 (LLM significantly beats this
    reviewer under the cost-benefit penalty ε=0.15).
  - Open dot = not rejected.
  - Vertical lines at d̄=0 (tied) and d̄=ε=0.15 (the H_0 boundary).
  - ω + rejection count annotated per judge block.

  uv run python scripts/fig_calderon_per_reviewer.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

HERE = Path(__file__).resolve().parent.parent
PROCESSED = HERE / "data" / "processed"
ASSETS = HERE / "assets"

# Match fig-judge-calibration's color scheme so a reader recognises the
# three judges across figures.
COLOURS = {
    "gpt-5-mini": "tab:blue",
    "gemini-3.1-pro-preview": "tab:green",
    "claude-opus-4-7": "tab:orange",
}
JUDGE_DISPLAY = {
    "gpt-5-mini": "GPT-5-mini",
    "gemini-3.1-pro-preview": "Gemini-3.1-Pro",
    "claude-opus-4-7": "Opus-4.7",
}
# Order judges by ω (worst-to-best on human picks) so the visual sweep is
# fail → fail → pass top-to-bottom.
JUDGE_ORDER = ("gpt-5-mini", "gemini-3.1-pro-preview", "claude-opus-4-7")
JUDGE_KEYS = {
    ("gpt-5-mini", "human"): "cfgB_gpt5_human",
    ("gemini-3.1-pro-preview", "human"): "cfgB_gemini_human",
    ("claude-opus-4-7", "human"): "cfgB_opus_human",
    ("gpt-5-mini", "llm"): "cfgB_gpt5_llm",
    ("gemini-3.1-pro-preview", "llm"): "cfgB_gemini_llm",
    ("claude-opus-4-7", "llm"): "cfgB_opus_llm",
}

EPS = 0.15


def _label(gid):
    return gid.split("@")[0]  # → grader_01 / grader_02 / …


def plot_panel(ax, calderon, corpus, title):
    """Plot one corpus column. y-positions stacked: judge blocks separated
    by a row gap. ω annotated to the right of each block; judge name
    as a header above each block (not overlapping data)."""
    y = 0
    yticks, ytick_labels = [], []
    block_headers = []  # (y_top, judge, payload) for headers + ω

    for judge in JUDGE_ORDER:
        payload = (calderon.get(JUDGE_KEYS[(judge, corpus)]) or {}).get("payload") or {}
        entries = sorted(payload.get("per_annotator", []),
                         key=lambda e: _label(e["grader_id"]))
        if not entries:
            continue
        y -= 0.6  # gap for header
        block_top_y = y + 0.3
        block_headers.append((block_top_y, judge, payload))
        y -= 0.4  # gap between header and first dot

        for entry in entries:
            d_bar = entry["d_bar"]
            rejected = entry.get("rejected_BY_FDR", False)
            colour = COLOURS[judge]
            ax.scatter(d_bar, y,
                       s=90,
                       facecolor=colour if rejected else "white",
                       edgecolor=colour,
                       linewidth=1.6,
                       zorder=3)
            ytick_labels.append(_label(entry["grader_id"]))
            yticks.append(y)
            y -= 1
        block_bottom_y = y + 0.5

        ax.axhspan(block_bottom_y, block_top_y,
                   color=COLOURS[judge], alpha=0.07, zorder=0)
        y -= 0.5  # gap to next block

    # Reference lines
    ax.axvline(0, color="grey", linewidth=0.9, linestyle="--", zorder=1)
    ax.axvline(EPS, color="black", linewidth=0.9, linestyle=":", zorder=1)
    ax.axvline(-EPS, color="black", linewidth=0.6, linestyle=":",
               alpha=0.4, zorder=1)

    # Judge headers + ω annotations (above each block)
    for block_top_y, judge, payload in block_headers:
        omega = payload.get("winning_rate")
        m = payload.get("m_annotators", 5)
        rej = sum(1 for e in payload["per_annotator"] if e.get("rejected_BY_FDR"))
        passes = payload.get("passes_alt_test")
        decision = "PASS ✓" if passes else "fail"
        # judge name on the left
        ax.text(-1.0, block_top_y + 0.15, JUDGE_DISPLAY[judge],
                ha="left", va="center",
                fontsize=10,
                fontweight="bold",
                color=COLOURS[judge])
        # ω + decision on the right
        omega_text = f"ω = {omega:.2f}  ({rej}/5)   {decision}"
        ax.text(1.0, block_top_y + 0.15, omega_text,
                ha="right", va="center",
                fontsize=10,
                fontweight="bold" if passes else "normal",
                color=COLOURS[judge])

    ax.set_yticks(yticks)
    ax.set_yticklabels(ytick_labels, fontsize=8)
    ax.set_xlim(-1.05, 1.05)
    ax.set_xlabel(r"$\bar{d}_j = \rho^h_j - \rho^f_j$"
                  + "\n(← LLM judge aligns more closely  |  human aligns more closely →)",
                  fontsize=9)
    ax.set_title(title, fontsize=11, pad=8)
    ax.set_ylim(y - 0.3, 1)
    ax.tick_params(axis="x", labelsize=9)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    # ε / 0 axis annotations
    ax.text(EPS, 1.02, r"$\varepsilon$", ha="center", va="bottom",
            fontsize=9, color="black", transform=ax.get_xaxis_transform())
    ax.text(0, 1.02, "0", ha="center", va="bottom",
            fontsize=9, color="grey", transform=ax.get_xaxis_transform())


def main():
    calderon = json.loads((PROCESSED / "calderon_per_judge.json").read_text())

    fig, axes = plt.subplots(1, 2, figsize=(12, 6.5), sharey=False,
                             gridspec_kw={"wspace": 0.55})

    plot_panel(axes[0], calderon, "human", "Human-authored picks (n=30, 28 for Opus)")
    plot_panel(axes[1], calderon, "llm",   "LLM-generated picks (n=15)")

    # Shared legend for fill convention
    legend_handles = [
        Line2D([0], [0], marker="o", linestyle="",
               markerfacecolor="grey", markeredgecolor="grey",
               markersize=9, label="rejected (BY-FDR q=0.05)"),
        Line2D([0], [0], marker="o", linestyle="",
               markerfacecolor="white", markeredgecolor="grey",
               markeredgewidth=1.6, markersize=9,
               label="not rejected"),
    ]
    fig.legend(handles=legend_handles, loc="lower center",
               bbox_to_anchor=(0.5, -0.02), ncol=2, frameon=False,
               fontsize=10)
    fig.suptitle(
        r"Calderon §3 alt-test, per blind reviewer (Config B, $\varepsilon=0.15$, "
        r"Benjamini–Yekutieli FDR at $q=0.05$). "
        r"Pass criterion: $\omega \geq 0.5$.",
        fontsize=11, y=0.995)
    fig.tight_layout(rect=[0, 0.04, 1, 0.96])

    out = ASSETS / "fig-calderon-per-reviewer.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=180, bbox_inches="tight")
    plt.close(fig)
    print(f"saved {out}")


if __name__ == "__main__":
    main()
