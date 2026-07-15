"""Offline, deterministic smoke evaluation. Replace mock cases with recorded provider outputs in CI."""
import argparse
import json
from pathlib import Path


def evaluate(path: str) -> dict:
    cases = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line]
    # This baseline validates dataset integrity; provider quality is evaluated from captured outputs.
    grounded = sum(case["deadline"] is None or isinstance(case["deadline"], str) for case in cases)
    return {"cases": len(cases), "deadline_grounding_rate": grounded / max(1, len(cases))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default="evals/data/golden.jsonl")
    args = parser.parse_args()
    result = evaluate(args.dataset)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["deadline_grounding_rate"] >= 0.95 else 1)
