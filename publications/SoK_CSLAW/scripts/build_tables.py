"""Write the systematization tables from data/*.yaml to assets/*.tex.

The manuscript \\input's these files, so the coding of every surveyed work and
paradigm lives in one reviewable place (data/) and the tables cannot drift from
it. Run via `make tables` (part of `make render`).
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ASSETS = ROOT / "assets"

MARK = {"+": r"\mfull", "o": r"\mhalf", "-": r"\mnone", "?": r"\mnt"}


def load(name):
    return yaml.safe_load((DATA / name).read_text(encoding="utf-8"))


def esc(s):
    """Escape plain-text fields; fields holding LaTeX (src) are passed raw."""
    for a, b in (("&", r"\&"), ("%", r"\%"), ("#", r"\#"), ("_", r"\_")):
        s = s.replace(a, b)
    return s


def col(w):
    """A ragged-right paragraph column of the given share of the line width."""
    return rf">{{\raggedright\arraybackslash}}p{{{w}\linewidth}}"


def table(label, caption, colspec, header, rows, size=r"\footnotesize", note=None, star=False, placement="t"):
    """Every table spans the full text width (tabular* with stretched column gaps)."""
    env = "table*" if star else "table"
    out = [rf"\begin{{{env}}}[{placement}]", rf"\caption{{{caption}}}", rf"\label{{{label}}}", r"\centering", size,
           rf"\begin{{tabular*}}{{\linewidth}}{{@{{\extracolsep{{\fill}}}}{colspec}@{{}}}}", r"\toprule", " & ".join(header) + r" \\", r"\midrule"]
    for r in rows:
        out.append(r"\midrule" if r == "MIDRULE" else " & ".join(r) + r" \\")
    out += [r"\bottomrule", r"\end{tabular*}"]
    if note:
        out += [r"\par\smallskip", rf"\parbox{{\linewidth}}{{\footnotesize {note}}}"]
    out.append(rf"\end{{{env}}}")
    return "\n".join(out) + "\n"


def paradigms():
    d = load("paradigms.yaml")
    des = d["desiderata"]
    header = ["", "Paradigm"] + [rf"\rotatebox{{70}}{{{x['short']}}}" for x in des]
    rows = [[p["id"], esc(p["name"])] + [MARK[p["marks"][x["id"]]] for x in des] for p in d["paradigms"]]
    note = (r"\mfull{} supported; \mhalf{} partly or under conditions; \mnone{} contradicted; \mnt{} not tested. "
            r"Marks rate the evidence, not what a design could achieve; Section~\ref{sec-paradigms} discusses the evidence behind the marks.")
    return table("tab:paradigms", "Evaluation paradigms against the desiderata of Section~\\ref{sec-desiderata}.",
                 "ll" + "c" * len(des), header, rows, note=note)


def studies():
    d = load("legal_studies.yaml")["studies"]
    rows = [[rf"{esc(s['name'])} \cite{{{s['key']}}}: {esc(s['setting'])}", s["paradigm"], esc(s["rubric"]),
             esc(s["ref"]), esc(s["judge"]), esc(s["human"])] for s in d]
    return table("tab:studies", "Automatic graders of open-text legal answers, by paradigm. \\emph{Judge}: "
                 "agreement with the reference in \\emph{Compared with}, model stability marked as such; "
                 "\\emph{Human}: reliability of the human grades, between or within graders; \\emph{reused}: "
                 "data or instruments shared with another cited study; n/r: not reported. QWK: quadratic weighted kappa; SPA: soft pairwise accuracy; IAA, IRR: inter-annotator agreement and reliability; MAE: mean absolute error; $W$ and $\\tau$: Kendall\'s; $\\alpha$: Krippendorff\'s.",
                 col(.25) + "l" + col(.16) + col(.12) + col(.19) + col(.17),
                 ["Study and setting", "P", "Rubric", "Compared with", "Judge", "Human"], rows,
                 size=r"\scriptsize\setlength{\tabcolsep}{2pt}\renewcommand{\arraystretch}{0.95}", star=True)


def requirements():
    d = load("requirements.yaml")["requirements"]
    rows = [[r["id"], esc(r["req"]), r["src"], esc(r["impl"]), esc(r["gap"])] for r in d]
    return table("tab:requirements", "What the law asks of grading open-text exam answers (L1 to L4 German "
                 "examination law, L5 to L7 EU law), the implementation we propose (Section~\\ref{sec-trust}) and "
                 "what is still open.",
                 "l" + col(.27) + col(.17) + col(.26) + col(.19),
                 ["", "Requirement", "Source", "Proposed implementation", "Open"], rows,
                 size=r"\scriptsize\setlength{\tabcolsep}{3pt}")


def design():
    d = load("design.yaml")["dimensions"]
    rows = [[esc(x["dim"]), esc(x["options"]), esc(x["basis"])] for x in d]
    return table("tab:design", "The design space of legal grading rubrics; the option we propose is listed first.",
                 col(.18) + col(.46) + col(.32),
                 ["Dimension", "Options", "Evidence and law"], rows,
                 size=r"\scriptsize\setlength{\tabcolsep}{3pt}")


def main():
    ASSETS.mkdir(exist_ok=True)
    for name, fn in (("tbl_paradigms", paradigms), ("tbl_studies", studies), ("tbl_requirements", requirements),
                     ("tbl_design", design)):
        (ASSETS / f"{name}.tex").write_text(fn(), encoding="utf-8")
        print(f"wrote assets/{name}.tex")


if __name__ == "__main__":
    main()
