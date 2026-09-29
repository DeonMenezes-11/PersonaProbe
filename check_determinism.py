"""
Is the model deterministic at temperature 0?

Asks 10 fixed questions 3 times each and compares the answers. The result
decides the study design (one answer per question if identical, three repeats
if not) and is saved to cache/determinism.json for the Reliability tab.

Run:  python check_determinism.py [model]
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from personas import PERSONAS, SCENARIOS
from runner import MODEL, call, parse_response

OUT = Path(__file__).parent / "cache" / "determinism.json"
PAIRS = [("rec_laptop", "P0_baseline"), ("rec_laptop", "P7_rural"),
         ("rec_phone", "P7_rural"), ("rec_phone", "P6_disability"),
         ("rec_tablet", "P0_baseline"), ("loan", "P0_baseline"),
         ("loan_b", "P0_baseline"), ("hiring_b", "P5_age_old"),
         ("tenancy_b", "P7_rural"), ("admission_b", "P3_caste")]
REPEATS = 3


def main(model: str) -> None:
    sc_by, p_by = {s.id: s for s in SCENARIOS}, {p.id: p for p in PERSONAS}
    rows = []
    for sid, pid in PAIRS:
        sc = sc_by[sid]
        outs = [call(sc.build(p_by[pid]), 0.0, model) for _ in range(REPEATS)]
        parsed = [parse_response(o, sc.kind) for o in outs]
        key = (lambda d: (d["decision"], d["score"])) if sc.kind == "decision" \
            else (lambda d: (d["item"], d["price_inr"]))
        rows.append({"scenario": sid, "persona": pid,
                     "same_text": len(set(outs)) == 1,
                     "same_answer": len({key(d) for d in parsed}) == 1,
                     "answers": [key(d) for d in parsed]})
        print(f"{sid:12s} {pid:14s} same text: {rows[-1]['same_text']!s:5s} "
              f"same answer: {rows[-1]['same_answer']!s:5s} {rows[-1]['answers'][0]}")
    res = {"model": model, "repeats": REPEATS, "questions": len(rows),
           "same_text": sum(r["same_text"] for r in rows),
           "same_answer": sum(r["same_answer"] for r in rows),
           "ts": datetime.now(timezone.utc).isoformat(), "rows": rows}
    OUT.write_text(json.dumps(res, indent=2, default=str))
    print(f"\n{res['same_answer']}/{res['questions']} gave the same answer every time; "
          f"{res['same_text']}/{res['questions']} identical word for word -> {OUT.name}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else MODEL)
