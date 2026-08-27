#!/usr/bin/env python3
"""Rank agreement between the two full pipelines on ZJS (the paper's S 6 claim).

LEXam side: per-model mean judge score from data/judge_cells.tsv (lexam-open,
ZJS). Rubric side: per-model mean llm_judge_falloesung score from
data/paired_wide.csv (gpt-5.4-mini judge configs). Reports both rankings and
the number of discordant pairs.

Reference output (2026-08-14): 11 overlapping models, exactly 1 discordant
(adjacent) pair - Qwen3.5-122B vs Qwen3.6-27B. Caveat: the rubric-side dump
still contains superseded duplicate generations (e.g. Qwen3.5-122B n=863 on
581 tasks), and paired_wide.csv carries no generation timestamps, so this
script cannot dedup on its own.

Canonical dedup EXECUTED against the prod DB (2026-08-27), keeping the
latest generation per (task, model):

    SELECT DISTINCT ON (te.task_id, g.model_id) ...
    ORDER BY te.task_id, g.model_id, g.created_at DESC

Result: every model at n=581, Qwen3.5-122B rubric mean 44.2 (41.3 with the
dupes), and the two rankings agree EXACTLY - 0 discordant pairs. The paper
now states the deduped result; running this script on the shipped CSV shows
the conservative 1-swap variant.
"""

from itertools import combinations
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
ZJS = "0fefa5c8-29c7-4eb5-b107-c2271f2288f9"


def main() -> None:
    cells = []
    with open(HERE / "data" / "judge_cells.tsv") as f:
        hdr = f.readline().strip().split("\\t")  # dump uses literal backslash-t separators
        idx = {c: i for i, c in enumerate(hdr)}
        for line in f:
            p = line.rstrip("\n").split("\\t")
            if (len(p) >= len(hdr) and p[idx["project"]] == "ZJS Fälle"
                    and p[idx["structure_key"]] == "lexam-open" and not p[idx["annotation_id"]]):
                cells.append((p[idx["model_id"]], float(p[idx["score"]]) * 100))
    lexam = pd.DataFrame(cells, columns=["model", "score"]).groupby("model")["score"].mean()

    wide = pd.read_csv(HERE / "data" / "paired_wide.csv")
    z = wide[wide["project"] == ZJS].dropna(subset=["rubric"])
    rubric = z.groupby("model")["rubric"].mean() * 100

    common = sorted(set(lexam.index) & set(rubric.index), key=lambda m: -lexam[m])
    df = pd.DataFrame({"lexam": lexam[common], "rubric": rubric[common]}).loc[common]
    df["rank_lexam"] = df["lexam"].rank(ascending=False).astype(int)
    df["rank_rubric"] = df["rubric"].rank(ascending=False).astype(int)
    print(df.round(2).to_string())

    disc = sum(
        1 for a, b in combinations(common, 2)
        if (df.loc[a, "rank_rubric"] - df.loc[b, "rank_rubric"])
        * (df.loc[a, "rank_lexam"] - df.loc[b, "rank_lexam"]) < 0
    )
    print(f"\noverlapping models: {len(common)}  discordant pairs: {disc}")
    print("gap (rubric - lexam) per model:")
    print((df["rubric"] - df["lexam"]).round(1).to_string())


if __name__ == "__main__":
    main()
