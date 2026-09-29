# PersonaProbe

**Counterfactual Bias Auditing and Guardrail Mitigation of LLM Decision Advisors**

EAIDS Mini Project · Group 4 · Div/Batch B1
Aishwarya Gawali (16014223007) · Deon Menezes (16014223030)

---

## What it does

An LLM is asked to make a consequential decision — approve a loan, shortlist a
candidate, triage a patient. The request is held **byte-identical**; only the
applicant's identity changes (gender, religion- or caste-coded name, age,
disability, rural/metro origin). A fair decider must return the same answer for
everyone.

PersonaProbe measures whether it does, attributes the effect to a specific
identity attribute, then applies an anti-discrimination guardrail prompt and
**re-runs the identical probe set to measure whether the guardrail worked.**

Method follows Tamkin et al. (2023), *Evaluating and Mitigating Discrimination
in Language Model Decisions* (arXiv:2312.03689).

## Why this topic

Groups 1–3 all audit a **tabular classifier** making a resource-allocation
decision (loan, loan, welfare) — structurally the same project three times.
PersonaProbe audits a **generative model** instead, anchored on Experiment 4,
which no other group has taken.

| | Groups 1–3 | PersonaProbe |
|---|---|---|
| Audited artifact | Tabular classifier | Generative LLM |
| Input | CSV dataset | Counterfactual prompt pairs |
| Attribution | SHAP | Leave-one-out ablation |
| Anchor experiment | Exp 5 + 6 | **Exp 4 + 5** |
| Outcome | Bias diagnosed | Bias diagnosed **and mitigated, with the fix measured** |

## Lab experiments demonstrated (7 of 8)

| Exp | Where |
|---|---|
| **4** Cost-as-a-Proxy | 10 recommendation scenarios (laptop, phone, tablet, headphones, monitor, printer, backpack, mixer grinder, course, diagnostic tests) — price of what each persona is steered to |
| **5** Fairness + XAI dashboard | `metrics.py`, `ablate.py`, `app.py` |
| 1 Ethical analysis | AIA report §1, §6 |
| 2 Dataset bias | The persona bank is itself a constructed dataset — §6 documents its own sampling bias |
| 6 UNESCO/IEEE AIA | `report.py` |
| 7 Degradation/stability | Determinism check, cross-model replication, pinned versions (`check_determinism.py`, `--model`) |
| 8 Regulations | AIA report §7, incl. the India DPDP gap analysis |

---

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env        # then paste OPENAI_API_KEY (and GEMINI_API_KEY for the replication)
```

## Run

```bash
python test_personaprobe.py                      # verify the pipeline (no API needed)
python make_fixture.py                           # synthetic data to develop against
python check_determinism.py                      # same answer twice at temperature 0?
python runner.py --condition baseline --repeats 3 --workers 8                    # 660 calls
python runner.py --condition mitigated --repeats 3 --workers 8                   # decision guardrail
python runner.py --condition mitigated_rec --kind recommend --repeats 3 --workers 8
python runner.py --model gemini-3.1-flash-lite --condition baseline              # replication
python metrics.py baseline                       # numbers
python ablate.py baseline                        # attribution
python report.py baseline                        # -> out/AIA_report.md
streamlit run app.py                             # dashboard (run from this folder)
python capture_screens.py                        # screenshots for the guide (dashboard running)
python make_explainer.py                         # -> out/PersonaProbe_Explained.pdf
python make_report.py                            # -> out/PersonaProbe_Project_Report.pdf + .docx (formal report)
```

Everything after `runner.py` reads the cache only — **no network, no API key.**
The cache (`cache/responses.jsonl`) is committed, so the dashboard and every
report can be reproduced without calling any API.

## Deploy the dashboard (Streamlit Community Cloud)

1. Sign in at [share.streamlit.io](https://share.streamlit.io) with GitHub.
2. **Create app → Deploy a public app from GitHub**: repository
   `DeonMenezes-11/PersonaProbe`, branch `main`, main file `app.py`.
3. Under **Advanced settings**, choose Python 3.12 (or 3.13). No secrets are
   needed: the dashboard only reads the committed cache.
4. **Deploy.** Every push to `main` redeploys automatically.

## The dashboard

Seven tabs, in the order of the demo. Each tab opens with badges naming the lab
experiments it demonstrates, and the Overview tab has the full experiment map.

| Tab | Shows | Lab experiments |
|---|---|---|
| ① Overview | The idea, how it works, the four headline findings, experiment map; model switch in the header | all |
| ② The test | Ten people plus a no-identity control, twenty situations, side-by-side prompt comparer | Exp 1, Exp 2 |
| ③ Decisions | Clear-cut and borderline approvals, score heatmap, which detail moved the score | Exp 5 |
| ④ Recommendations | Product and price offered to each person; the AI's own words; consistency across categories | Exp 4, Exp 5 |
| ⑤ Guardrails | Both guardrails, two fairness measures, what no guardrail could fix | Exp 6, Exp 5 |
| ⑥ Ethics & law | UNESCO/IEEE mapping, EU AI Act risk classes, law-coverage gaps, downloads | Exp 6, Exp 8 |
| ⑦ Reliability | Two-model comparison, determinism check, the retired-model episode | Exp 7 |

The light theme is locked in `.streamlit/config.toml`, so run Streamlit from this
folder for it to apply. The test suite runs the dashboard headlessly: it exercises
every control, checks that no internal ID is visible, and checks that the headline
numbers on screen match the analysis.

---

## Design decisions worth defending in the viva

**1. Structured JSON output.** Every prompt ends with a JSON response contract.
This turns the project from an NLP problem into a pandas problem — no sentiment
models, no embeddings, no classifiers. It is the single biggest complexity saver
in the design.

**2. Byte-identical prompts.** `validate_prompts()` asserts that within a
scenario every prompt is identical once the persona phrase is masked. If this
fails, no downstream number means anything. It is test #1 for that reason.

**3. Ablation, not SHAP.** SHAP needs a feature vector and model internals; the
audited model is a closed API with neither. Each persona differs from baseline
by exactly one attribute, so its score gap *is* that attribute's marginal
contribution, measured directly. Same idea as a single-feature Shapley value —
but we do not claim the SHAP name for it.

**4. Cache-first.** Every response is written to `cache/responses.jsonl`, keyed
by a hash of prompt+model+temp+condition. Re-runs are free, a crashed run
resumes, and **the demo runs with the wifi off.** The cache is committed
deliberately (not gitignored) so every number in the report is reproducible.

**5. Refusals and parse failures are data.** A refusal that varies by persona is
a finding. Dropping unparseable rows silently would bias the results, so they
are counted and reported.

**6. Report the mitigation result honestly.** If the guardrail only partly closes
the gap — or widens one — that is a real finding about the limits of
prompt-level mitigation, and a stronger viva answer than a suspiciously clean
result. The intervention is not tuned until the numbers look good.

---

**7. Two pinned models.** The main study uses OpenAI `gpt-4.1-mini-2025-04-14`
(a paid key). Every question was repeated on Google `gemini-3.1-flash-lite` as a
replication. Exact versions are pinned, never an alias like `latest`: the Gemini
model the plan started with was retired mid-project.

**8. Measured determinism, not assumed.** `check_determinism.py` asked 10
questions 3 times each at temperature 0. GPT-4.1 mini gave the same answer only 6
of 10 times, so every OpenAI question is asked **3 times** and results use the
average. Gemini was deterministic, so it gets one answer per question.

**9. JSON mode, thinking off.** Current Gemini models reason internally before
answering and ran out of output budget before emitting the JSON. Native JSON
mode plus `thinkingBudget: 0` fixed it, and audits the direct decision path a
latency-sensitive production system would actually use. `PP_THINKING=1` audits
the reasoning path instead.

**10. Prices compared within a scenario only.** A phone and a lab test have
nothing in common, so each price is a ratio to what the baseline persona was
offered *in the same scenario*, then averaged per persona.

---

## Results

Round 1 exposed weaknesses in our own test, and round 2 fixed them. The fixes
were written into the plan before any round-2 data existed: borderline applicants
(round 1 approved everyone), six more product categories, a no-identity control
("Person A, age 32"), and a second AI.

Main study: GPT-4.1 mini, 1,650 answers, 100% readable, 0 refused.
Replication: Gemini 3.1 Flash-Lite.

**1. Yes/no decisions: no significant bias.** Every clear-cut applicant was
approved. On borderline cases the reference person was approved *least* (40%, vs
up to 80%). If anything this tilts toward disadvantaged-sounding applicants, the
"positive discrimination" Tamkin et al. also report. It is not significant
(p = 0.45), so we don't claim it. Gemini shows the same shape.

**2. Product advice: not fair.** Across 8 product categories, the rural persona
was offered **68%** of the reference price on average: cheaper in 5, the same in
3, **never more expensive** (sign test p = 0.06). On Gemini it was 43% (cheaper in
7 of 9). The wheelchair user was pushed up (168% on GPT, 123% on Gemini).
Examples: headphones for the rural persona were a Sony WH-CH710N at ₹6,990, while
everyone else got a Sony WH-1000XM5 at ₹29,990.

**3. In its own words.** 57% of GPT's reasons for the rural persona used budget
words ("affordable", "budget-friendly"), against 23% for the reference person
(Gemini: 40% vs 10%). No prompt mentioned a budget. The wheelchair user's
disability came up in 67% (GPT) and 70% (Gemini) of their reasons.

**4. Compared with no identity at all.** Against "Person A" (no name, no hometown),
almost every named person, Rahul included, was offered cheaper products. Rural
was lowest. Naming someone seems to pull advice down, and rural background
pulls it furthest.

**5. Guardrails changed the words, not the treatment.** Overall consistency
improved slightly with both guardrails, mostly because fewer people were pushed
up. But for the rural persona, mentions of their background fell from **43% to
0%** while the price they were offered went from 68% to 57–63% of the reference.
The AI obeyed the instruction about *words* and kept the *behaviour*. Gemini
did the same: mentions of the rural background went from 40% to 0%, and the price
offered from 43% to 39%. So an AI's explanation is not evidence that it is fair.

**6. Both models together (post hoc).** Pooling every category on both models,
the rural persona was cheaper in 12 and more expensive in 1 (p = 0.003). We
added this test after seeing the results, so it is supporting evidence, not the
main claim.

**7. Lessons about measuring.**
- Yes/no metrics would have called this AI fair.
- A single reference answer can mislead, so we use three reference points.
- Borderline cases are needed for bias to show at all.

---

## Limitations

- Name-coding is an imperfect proxy for identity; the persona bank is
  India-centric and covers 8 axes plus one intersection.
- The model self-reports a confidence score — a stated number, not an internal
  probability.
- Prompt-level mitigation constrains stated reasoning, not the underlying
  representation. Residual gaps are expected and are reported as measured.
- Findings are specific to the model and prompt version tested. The probe set is
  a **regression test**, not a one-time certificate.

## References

- Tamkin et al. (2023), *Evaluating and Mitigating Discrimination in Language
  Model Decisions*, arXiv:2312.03689 — primary method paper
- Parrish et al. (2022), *BBQ: A Hand-Built Bias Benchmark for Question
  Answering*, ACL Findings — probe design
- UNESCO *Recommendation on the Ethics of AI* (2021)
- IEEE *Ethically Aligned Design*
- EU AI Act — Art. 5, 10, 14, 27; Annex III
- India DPDP Act 2023; NITI Aayog *Responsible AI for All*
