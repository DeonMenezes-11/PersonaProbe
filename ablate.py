"""
Leave-one-attribute-out attribution.

SHAP does not apply to a closed API model - there is no feature vector and no
access to internals. The honest substitute is ablation: every persona already
differs from baseline by exactly ONE attribute, so each persona's score gap IS
that attribute's marginal contribution, measured directly.

Call this ablation-based attribution, NOT SHAP. It is the same idea as a
Shapley marginal contribution computed over a single feature, but claiming the
SHAP name for it would not survive a viva.

Bonus (costs zero extra API calls): decompose the intersectional persona to
test whether combined identity effects are additive or super-additive.
"""

import sys
from pathlib import Path

import pandas as pd

import metrics as M

CACHE = Path(__file__).parent / "cache" / "responses.jsonl"


def attribution(df: pd.DataFrame) -> pd.DataFrame:
    """Rank identity attributes by how far they moved the mean score."""
    gaps = M.parity_gaps(df)
    out = gaps[["persona_id", "axis", "level", "score_gap", "parity_gap", "n"]].copy()
    out["abs_effect"] = out.score_gap.abs()
    out["direction"] = out.score_gap.apply(
        lambda x: "penalty" if x < 0 else "bonus" if x > 0 else "none")
    return out.sort_values("abs_effect", ascending=False).reset_index(drop=True)


def intersectional_decomposition(df: pd.DataFrame,
                                 combo="P8_intersect",
                                 parts=("P1_gender_f", "P2_religion")) -> dict:
    """
    Is the effect of holding two identities together equal to the sum of
    holding each alone? If the observed combined effect is LARGER than the sum,
    the harm is super-additive - a compounding effect that single-axis auditing
    would miss entirely.
    """
    g = M.parity_gaps(df).set_index("persona_id").score_gap
    missing = [p for p in (combo,) + tuple(parts) if p not in g.index]
    if missing:
        return {"error": f"missing personas: {missing}"}

    observed = float(g[combo])
    additive = float(sum(g[p] for p in parts))
    excess = observed - additive
    return {
        "combo": combo,
        "observed_effect": round(observed, 3),
        "sum_of_parts": round(additive, 3),
        "parts": {p: round(float(g[p]), 3) for p in parts},
        "excess_over_additive": round(excess, 3),
        # negative excess = combined penalty exceeds the sum of its parts
        "super_additive": bool(excess < -1.0),
    }


def report(condition: str = "baseline", path: Path = CACHE) -> None:
    df = M.load(condition, path)
    pd.set_option("display.width", 200)

    print(f"=== ablation attribution ({condition}) ===\n")
    a = attribution(df)
    print(a.to_string(index=False))

    print("\n=== intersectional decomposition ===")
    d = intersectional_decomposition(df)
    if "error" in d:
        print(d["error"])
        return
    for k, v in d.items():
        print(f"  {k}: {v}")
    if d["super_additive"]:
        print("\n  -> Combined identity penalty EXCEEDS the sum of its parts.")
        print("     Single-axis auditing would under-report this harm.")
    else:
        print("\n  -> Combined effect is approximately additive.")

    # Methodological caveat worth stating aloud in the demo.
    masked = a[(a.parity_gap.abs() < 1e-9) & (a.abs_effect > 2.0)]
    if not masked.empty:
        print("\n=== NOTE: bias hidden by the binary decision ===")
        print("  These personas show a real score penalty but NO change in the")
        print("  approve/deny outcome - the binary metric masks the bias:")
        for _, r in masked.iterrows():
            print(f"    {r.persona_id:16s} score {r.score_gap:+.2f}  decision gap 0.00")


if __name__ == "__main__":
    cond = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    p = Path(sys.argv[2]) if len(sys.argv) > 2 else CACHE
    report(cond, p)
