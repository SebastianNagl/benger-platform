"""Regenerate ``reference_values.json``: pyfixest on the synthetic design.

pyfixest is a second, independent implementation of fixed-effects OLS with
cluster-robust inference (it mirrors R fixest). It is not in the workers
image (it pulls in plotting and notebook stacks), so its results on the
synthetic role-swap design are recorded here and the engine is compared with
them in ``test_analysis_cross_checks.py``.

The data are built straight from the records with pandas, not through the
engine's frame builder, so the check also covers the measure coding.

Run with pyfixest, pandas and numpy installed (versions are recorded):

    python -I services/workers/tests/analysis/make_reference_values.py
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def frame():
    import pandas as pd

    sys.path.insert(0, HERE)
    from analysis_synthetic import role_swap_records

    rows = []
    for r in role_swap_records():
        if "share_p" not in r["fields"]:
            continue
        f = r["variant"]["factors"]
        x_p = 1.0 if f["x_role"] == "P" else 0.0
        share_p = float(r["fields"]["share_p"])
        rows.append(
            {
                "unit": r["variant"]["unit"],
                "system": r["model_id"],
                "name_id": f["name_id"],
                "scenario": f["scenario"],
                "level": float(f["level"]),
                "x_p": x_p,
                "first_x": 1.0 if f["x_role"] == f["first"] else 0.0,
                "share_x": share_p if x_p == 1 else 100.0 - share_p,
            }
        )
    return pd.DataFrame(rows)


CASES = [
    # id, formula, vcov, ssc keyword arguments
    ("within_crv_unit_matched", "share_x ~ x_p + first_x | unit:system", {"CRV1": "unit"}, {"k_fixef": "none", "G_df": "conventional"}),
    ("within_crv_two_way_matched", "share_x ~ x_p + first_x | unit:system", {"CRV1": "unit+name_id"}, {"k_fixef": "none", "G_df": "conventional"}),
    ("within_crv_unit_fixest", "share_x ~ x_p + first_x | unit:system", {"CRV1": "unit"}, {}),
    ("within_crv_two_way_fixest", "share_x ~ x_p + first_x | unit:system", {"CRV1": "unit+name_id"}, {}),
    ("within_iid_fixest", "share_x ~ x_p + first_x | unit:system", "iid", {}),
    ("within_hetero_fixest", "share_x ~ x_p + first_x | unit:system", "hetero", {}),
    ("two_sets_crv_unit_fixest", "share_x ~ level + x_p + first_x | system + name_id", {"CRV1": "unit"}, {}),
]


def main() -> None:
    import numpy
    import pandas
    import pyfixest as pf

    data = frame()
    out = {
        "generator": "pyfixest",
        "versions": {"pyfixest": pf.__version__, "pandas": pandas.__version__, "numpy": numpy.__version__},
        "rows": int(len(data)),
        "cases": {},
    }
    # The default demeaners stop at a tolerance of 1e-8 or 1e-6; the engine
    # converges to 1e-12, so the reference uses a tight tolerance as well.
    demeaner = pf.MapDemeaner(fixef_tol=1e-14)
    for case_id, formula, vcov, ssc in CASES:
        fit = pf.feols(formula, data=data, vcov=vcov, ssc=pf.ssc(**ssc), demeaner=demeaner)
        tidy = fit.tidy()
        out["cases"][case_id] = {
            "formula": formula,
            "vcov": vcov,
            "ssc": ssc,
            "n": int(fit._N),
            "coefficients": {
                name: {
                    "estimate": float(tidy.loc[name, "Estimate"]),
                    "std_error": float(tidy.loc[name, "Std. Error"]),
                    "p_value_t": float(tidy.loc[name, "Pr(>|t|)"]),
                    "ci_lower_t": float(tidy.loc[name, "2.5%"]),
                    "ci_upper_t": float(tidy.loc[name, "97.5%"]),
                }
                for name in tidy.index
            },
        }
    path = os.path.join(HERE, "reference_values.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
        fh.write("\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
