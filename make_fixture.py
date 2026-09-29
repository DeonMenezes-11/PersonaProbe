"""
Generate a SYNTHETIC response set with a known, planted bias.

Purpose: let the metrics/dashboard half be built and verified before any real
API run exists, and prove the metrics actually detect a bias of known size and
direction. Writes to cache/fixture.jsonl - NEVER to the real cache.

!! Numbers produced from this file are synthetic and must never appear in the
!! report as findings. The report uses cache/responses.jsonl only.
"""

import json
import random
from datetime import datetime, timezone
from pathlib import Path

from personas import SCENARIOS, PERSONAS
from runner import cache_key, CONDITIONS

OUT = Path(__file__).parent / "cache" / "fixture.jsonl"

# Planted effect: score penalty per axis, in points, applied under "baseline".
# The mitigated condition shrinks each penalty to 25% of its size - so the
# comparison table has a known-correct answer to check against.
PLANTED = {
    "none": 0.0, "gender": -4.0, "religion": -9.0, "caste": -11.0,
    "age": -3.0, "disability": -6.0, "location": -7.0,
    "intersectional": -14.0, "class": -5.0,
}
BASE_SCORE = 74.0
APPROVE_AT = 60.0
PRICE_BASE = 62000.0


def main(seed: int = 7) -> None:
    rng = random.Random(seed)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        OUT.unlink()

    n = 0
    with OUT.open("a") as f:
        for condition in ("baseline", "mitigated", "mitigated_rec"):
            shrink = {"baseline": 1.0, "mitigated": 0.25, "mitigated_rec": 0.1}[condition]
            prefix = CONDITIONS[condition]
            for sc in SCENARIOS:
                # the recommendation guardrail only covers recommend scenarios
                if condition == "mitigated_rec" and sc.kind != "recommend":
                    continue
                for p in PERSONAS:
                    for r in range(3):
                        prompt = prefix + sc.build(p)
                        penalty = PLANTED.get(p.axis, 0.0) * shrink
                        rec = {
                            "key": cache_key(prompt, "FIXTURE", 0.0, condition, r),
                            "scenario_id": sc.id, "kind": sc.kind,
                            "persona_id": p.id, "axis": p.axis, "level": p.level,
                            "repeat": r, "condition": condition,
                            "model": "FIXTURE-synthetic", "temperature": 0.0,
                            "prompt": prompt, "raw": "<synthetic>", "error": None,
                            "ts": datetime.now(timezone.utc).isoformat(),
                            "refused": False, "parse_ok": True,
                            "reason": "synthetic fixture row",
                            "decision": None, "score": None,
                            "item": None, "price_inr": None,
                        }
                        if sc.kind == "decision":
                            score = BASE_SCORE + penalty + rng.gauss(0, 3.0)
                            rec["score"] = round(score, 1)
                            rec["decision"] = "approve" if score >= APPROVE_AT else "deny"
                        else:
                            # Exp 4: cheaper recommendations for penalised personas
                            rec["price_inr"] = round(
                                PRICE_BASE + penalty * 900 + rng.gauss(0, 2000), -2)
                            # distinct names: a different price is a different item
                            rec["item"] = f"Synthetic {sc.id} model {int(rec['price_inr'])}"
                        f.write(json.dumps(rec) + "\n")
                        n += 1

    print(f"wrote {n} synthetic rows -> {OUT}")
    print("planted penalties (baseline, points):",
          {k: v for k, v in PLANTED.items() if v})
    print("mitigated shrinks each penalty to 25%; mitigated_rec (recommend only) to 10%")


if __name__ == "__main__":
    main()
