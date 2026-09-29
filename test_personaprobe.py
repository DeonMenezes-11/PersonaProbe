"""
Verification suite. Run:  python test_personaprobe.py

Test 1 is the one that matters most: if prompts differ beyond the persona
slot, every number downstream is meaningless.
"""

import json
import sys
from pathlib import Path

import pandas as pd

import ablate
import metrics as M
from make_fixture import PLANTED
from personas import PERSONAS, SCENARIOS, validate_prompts
from runner import (parse_response, _is_daily_quota, provider, _openai_body,
                    PRIMARY_MODEL, REPLICATION_MODEL)

FIX = Path(__file__).parent / "cache" / "fixture.jsonl"
fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""))
    if not cond:
        fails.append(name)


print("\n1. Prompt validity (the validity backbone)")
try:
    validate_prompts()
    check("prompts byte-identical except persona slot", True,
          f"{len(SCENARIOS)} scenarios x {len(PERSONAS)} personas")
except AssertionError as e:
    check("prompts byte-identical except persona slot", False, str(e))

check("exactly one persona slot per template",
      all(s.template.count("{persona}") == 1 for s in SCENARIOS))
check("each persona varies one axis",
      len({p.axis for p in PERSONAS}) >= 7,
      f"{len({p.axis for p in PERSONAS})} axes")

FAIR = [p for p in PERSONAS if p.id != M.CONTROL_ID]   # personas under test

print("\n1b. Round-2 design")
by_id = {p.id: p for p in PERSONAS}
check("reference persona's wording unchanged (old cache keys stay valid)",
      by_id["P0_baseline"].phrase() == "Rahul Sharma, age 32, from Mumbai")
check("identity-blank control has no name or hometown",
      by_id[M.CONTROL_ID].phrase() == "Person A, age 32")
check("borderline versions of all five decisions exist",
      all(s + "_b" in {x.id for x in SCENARIOS} for s in M.DEC_CLEAR))
check("ten recommendation categories",
      sum(x.kind == "recommend" for x in SCENARIOS) == 10)
check("provider routing", provider(PRIMARY_MODEL) == "openai"
      and provider(REPLICATION_MODEL) == "gemini")
body = _openai_body("Respond ONLY with JSON", 0.0, PRIMARY_MODEL)
check("OpenAI request: JSON mode, temperature 0, fixed seed",
      body["response_format"] == {"type": "json_object"} and body["temperature"] == 0.0
      and "seed" in body and len(body["messages"]) == 1)
check("budget lexicon", bool(M.BUDGET_WORDS.search("ideal within a budget-friendly range"))
      and not M.BUDGET_WORDS.search("excellent performance for Python"))
check("identity lexicon matches the persona's own trait only",
      bool(__import__("re").search(M.IDENTITY_WORDS["location"], "suitable for rural areas"))
      and not __import__("re").search(M.IDENTITY_WORDS["location"], "suitable for video meetings"))

print("\n2. Response parsing")
check("clean json", parse_response('{"decision":"approve","score":80,"reason":"x"}',
                                   "decision")["decision"] == "approve")
check("fenced json", parse_response('```json\n{"decision":"deny","score":20,"reason":"x"}\n```',
                                    "decision")["decision"] == "deny")
check("preamble tolerated",
      parse_response('Sure!\n{"decision":"approve","score":70,"reason":"x"}',
                     "decision")["parse_ok"])
check("refusal flagged", parse_response("I cannot make that call.", "decision")["refused"])
check("garbage not silently dropped",
      parse_response("no json here", "decision")["parse_ok"] is False)
check("invalid decision rejected",
      parse_response('{"decision":"maybe","score":50,"reason":"x"}',
                     "decision")["parse_ok"] is False)
check("recommend contract",
      parse_response('{"item":"X","price_inr":50000,"reason":"y"}',
                     "recommend")["price_inr"] == 50000)
check("price given as a formatted string",
      parse_response('{"item":"X","price_inr":"INR 1,24,900","reason":"y"}',
                     "recommend")["price_inr"] == 124900)


class _Resp:
    def __init__(self, body): self._b = body
    def json(self): return self._b


_daily = {"error": {"details": [{"violations": [
    {"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}}
_minute = {"error": {"details": [{"violations": [
    {"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]}]}}
check("daily quota 429 detected (stop, don't retry)", _is_daily_quota(_Resp(_daily)))
check("per-minute 429 not mistaken for daily", not _is_daily_quota(_Resp(_minute)))

print("\n3. Metrics recover a planted bias")
if not FIX.exists():
    check("fixture exists", False, "run: python make_fixture.py")
else:
    df = M.load("baseline", FIX)
    gaps = M.parity_gaps(df).set_index("persona_id")
    axis_of = {p.id: p.axis for p in PERSONAS}

    recovered, expected = [], []
    for pid, row in gaps.iterrows():
        ax = axis_of[pid]
        if PLANTED.get(ax, 0):
            recovered.append(row.score_gap)
            expected.append(PLANTED[ax])
    corr = pd.Series(recovered).corr(pd.Series(expected))
    check("recovered gaps correlate with planted bias", corr > 0.9, f"r={corr:.3f}")
    check("all planted penalties recovered as penalties",
          all(v < 0 for v in recovered))
    check("worst persona is the intersectional one",
          M.disparate_impact(df)["worst_persona"] == "P8_intersect")
    check("baseline fails four-fifths rule",
          M.disparate_impact(df)["passes_four_fifths"] is False)
    check("chi-square detects the difference",
          M.significance(df).get("decisions_differ_significantly") is True)

    print("\n4. Mitigation comparison")
    cmp_tbl = M.compare_conditions(FIX)
    check("all three conditions present", len(cmp_tbl) == 3)
    rec_row = cmp_tbl[cmp_tbl.condition == "mitigated_rec"]
    check("recommend-only condition: no decision metrics, price metrics present",
          len(rec_row) == 1 and pd.isna(rec_row.iloc[0].disparate_impact)
          and pd.notna(rec_row.iloc[0].price_parity_share))
    if len(cmp_tbl) >= 2:
        b = cmp_tbl[cmp_tbl.condition == "baseline"].iloc[0]
        m = cmp_tbl[cmp_tbl.condition == "mitigated"].iloc[0]
        check("mitigation shrinks max score gap",
              m.max_score_gap < b.max_score_gap,
              f"{b.max_score_gap:.2f} -> {m.max_score_gap:.2f}")
        check("mitigation improves disparate impact",
              m.disparate_impact >= b.disparate_impact,
              f"{b.disparate_impact:.3f} -> {m.disparate_impact:.3f}")

    print("\n4b. Cost-as-a-proxy across scenarios")
    cp = M.cost_proxy(df)
    base_rows = cp[cp.persona_id == "P0_baseline"]
    check("prices normalised within each scenario (baseline ratio = 1)",
          (base_rows.price_ratio.round(9) == 1.0).all(),
          f"{cp.scenario_id.nunique()} scenarios")
    pooled = M.cost_proxy_pooled(df)
    ax = pooled.persona_id.map(axis_of)
    r = pooled.mean_ratio.corr(ax.map(PLANTED))
    check("pooled price ratios track planted bias", r > 0.9, f"r={r:.3f}")
    check("worst price persona is the intersectional one",
          pooled.iloc[0].persona_id == "P8_intersect")
    if len(cmp_tbl) >= 2:
        check("mitigation raises share of cells at price parity",
              m.price_parity_share > b.price_parity_share,
              f"{b.price_parity_share:.3f} -> {m.price_parity_share:.3f}")
    tr = M.price_transitions(df, M.load("mitigated", FIX))
    check("transitions classify every cell",
          set(tr.status) <= {"parity", "fixed", "introduced", "persisted"}
          and len(tr) == (len(FAIR) - 1) * cp.scenario_id.nunique())

    print("\n4d. Anchor problem (why two measures)")
    # Nine personas all get 100; the baseline persona alone gets 150.
    toy = pd.DataFrame([{
        "scenario_id": "rec_x", "kind": "recommend", "parse_ok": True,
        "persona_id": p.id, "axis": p.axis, "level": p.level,
        "item": "Pricey" if p.id == "P0_baseline" else "Normal",
        "price_inr": 150.0 if p.id == "P0_baseline" else 100.0,
    } for p in FAIR])
    pp_toy = M.price_parity(toy, exclude=set())
    pc_toy = M.price_consensus(toy, exclude=set())
    check("anchored parity is fooled by an outlier baseline persona",
          pp_toy["at_parity"] == 0, f"{pp_toy['at_parity']}/{pp_toy['cells']}")
    check("median consensus is not", pc_toy["at_consensus"] == 9,
          f"{pc_toy['at_consensus']}/{pc_toy['cells']}")
    tt = M.price_transitions(df, M.load("mitigated", FIX), anchor="median")
    ok = all(((abs(r.price_ratio_base - 1) > M.PARITY_TOL) ==
              (r.status in ("fixed", "persisted"))) and
             ((abs(r.price_ratio_mit - 1) > M.PARITY_TOL) ==
              (r.status in ("introduced", "persisted"))) for _, r in tt.iterrows())
    check("transition ratios agree with their status (no '0.72 -> 0.62: fixed')", ok)
    check("median transitions include the baseline persona",
          "P0_baseline" in set(tt.persona_id))

    print("\n4c. Same-item detection (quote noise vs steering)")
    N = M._norm_item
    check("S23 vs S23 FE are different products",
          N("Samsung Galaxy S23") != N("Samsung Galaxy S23 FE"))
    check("spec parentheses ignored",
          N("Apple MacBook Air M3 (13-inch, 16GB RAM)") == N("Apple MacBook Air M3 (16GB RAM)"))
    check("platform suffix ignored",
          N("Google Data Analytics Professional Certificate via Coursera")
          == N("Google Data Analytics Professional Certificate"))
    check("fixture has no same-item scenarios (distinct synthetic items)",
          M.same_item_scenarios(df) == set())

    print("\n5. Attribution")
    a = ablate.attribution(df)
    check("attribution ranks all non-baseline personas", len(a) == len(FAIR) - 1)
    check("control excluded from fairness metrics",
          M.CONTROL_ID not in set(df.persona_id)
          and M.CONTROL_ID in set(M.load("baseline", FIX, include_control=True).persona_id))
    cs = M.category_signs(df)
    worst = cs.iloc[0]
    check("sign test flags the planted persona as consistently cheaper",
          worst.persona_id == "P8_intersect" and worst.cheaper == worst.categories
          and worst.p_value < 0.01, f"{worst.cheaper}/{worst.categories}, p={worst.p_value}")
    check("ranked by absolute effect",
          list(a.abs_effect) == sorted(a.abs_effect, reverse=True))
    check("intersectional decomposition computes",
          "error" not in ablate.intersectional_decomposition(df))

    print("\n6. Data hygiene")
    check("parse rate >= 95%", df.parse_ok.mean() >= 0.95, f"{df.parse_ok.mean():.1%}")
    check("fixture is labelled synthetic", str(df.model.iloc[0]).startswith("FIXTURE"))
    check("no real cache contaminated by fixture",
          not (Path("cache/responses.jsonl").exists() and
               "FIXTURE" in Path("cache/responses.jsonl").read_text()))

print("\n7. Dashboard (headless run of app.py)")
REAL = Path(__file__).parent / "cache" / "responses.jsonl"
if not REAL.exists():
    check("real cache exists (needed for the dashboard)", False, "run runner.py")
else:
    import re
    from streamlit.testing.v1 import AppTest

    APP = str(Path(__file__).parent / "app.py")
    at = AppTest.from_file(APP, default_timeout=120).run()
    check("dashboard runs without an exception", not at.exception,
          str(at.exception[0].value)[:120] if at.exception else "")

    # every option of every control must re-render cleanly
    controls = [("radio", w.key, list(w.options)) for w in at.radio] + \
               [("selectbox", w.key, list(w.options)) for w in at.selectbox]
    broken = []
    for kind, key, options in controls:
        for opt in options:
            getattr(at, kind)(key=key).set_value(opt).run()
            if at.exception:
                broken.append(f"{key}={opt}")
    check("every option of every control renders",
          not broken and len(controls) >= 7,
          f"{len(controls)} controls" + (f"; broken: {broken[:3]}" if broken else ""))

    # nothing a viewer sees may be an internal identifier
    at = AppTest.from_file(APP, default_timeout=120).run()
    shown = []
    for group in ("markdown", "caption", "subheader", "info", "warning", "success",
                  "metric", "radio", "selectbox", "expander"):
        for el in getattr(at, group):
            for attr in ("value", "body", "label", "options"):
                v = getattr(el, attr, None)
                if v is not None:
                    shown.append(str(v))
    for df_el in at.dataframe:
        v = df_el.value
        shown.append(" ".join(map(str, v.columns)) + " " + v.to_string())
    text = "\n".join(shown)
    raw = re.findall(r"\bP\d+_[A-Za-z]+|\brec_[a-z]+\b|"
                     r"\b(?:loan|hiring|admission|triage|tenancy)_b\b|"
                     r"\bmitigated(?:_rec)?\b|price_ratio|cells_at|persona_id|scenario_id",
                     text)
    check("no internal IDs shown to viewers", not raw, ", ".join(sorted(set(raw))[:5]))

    # the headline numbers on screen match the analysis
    cmp_real = M.compare_conditions(REAL, model=M.PRIMARY_MODEL)
    b_real = M.load("baseline", REAL, model=M.PRIMARY_MODEL)
    clear = b_real[b_real.scenario_id.isin(M.DEC_CLEAR) & (b_real.kind == "decision")]
    want = [f"{int((clear.decision == 'approve').sum())} of {len(clear)}"]
    want += [c.replace("/", " of ") for c in
             list(cmp_real.cells_at_parity) + list(cmp_real.cells_at_consensus)]
    ws = M.category_signs(b_real, exclude=M.shared_exclusion(REAL, model=M.PRIMARY_MODEL)).iloc[0]
    want.append(f"cheaper in {ws.cheaper} of {ws.categories} product categories")
    missing = [w for w in want if w not in text]
    check("headline numbers on screen match metrics", not missing,
          f"missing {missing}" if missing else ", ".join(want))

print("\n" + "=" * 58)
if fails:
    print(f"{len(fails)} FAILED: {', '.join(fails)}")
    sys.exit(1)
print("all checks passed")
