"""Summarise a run: automatic checks, human labels, per-slice breakdown.

The one thing this report insists on is confidence intervals. At n=20 the
95% interval on a pass rate is roughly +/-20 points, so "we improved from
80% to 85%" is noise. Reporting the interval alongside the number is what
stops an eval from producing confident nonsense — and being the person who
says so out loud is most of the value in a room full of stakeholders.

Wilson intervals rather than the normal approximation, because the normal
one falls apart at small n and at rates near 0 or 1, which is exactly where
this eval lives.

Usage:
    uv run python -m evals.report --tag baseline
"""

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

from evals.rubric import AUTOMATIC_CHECKS, CRITERIA, UNQUALIFIED

RESULTS_DIR = Path(__file__).parent / "results"


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a binomial proportion."""
    if total == 0:
        return (0.0, 0.0)
    rate = successes / total
    denominator = 1 + z**2 / total
    centre = (rate + z**2 / (2 * total)) / denominator
    spread = z * math.sqrt(rate * (1 - rate) / total + z**2 / (4 * total**2)) / denominator
    return (max(0.0, centre - spread), min(1.0, centre + spread))


def rate_line(name: str, successes: int, total: int) -> str:
    if total == 0:
        return f"  {name:<24} no data"
    low, high = wilson(successes, total)
    return (f"  {name:<24} {successes:>2}/{total:<2} "
            f"{successes / total:>6.0%}   95% CI [{low:.0%}, {high:.0%}]")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default="baseline")
    args = parser.parse_args()

    records = load_jsonl(RESULTS_DIR / f"run-{args.tag}.jsonl")
    if not records:
        raise SystemExit(f"no run found for tag '{args.tag}'")
    labels = {label["id"]: label for label in load_jsonl(RESULTS_DIR / f"labels-{args.tag}.jsonl")}
    meta_path = RESULTS_DIR / f"run-{args.tag}.meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}

    print(f"\nrun '{args.tag}'  model={meta.get('model', '?')}  "
          f"dataset={meta.get('dataset_version', '?')}  "
          f"prompt={meta.get('prompt_fingerprint', '?')}")
    print(f"{len(records)} items, {len(labels)} hand-labelled")

    # --- layer 1: automatic checks -------------------------------
    print("\nAUTOMATIC CHECKS (deterministic, free)")
    for check in AUTOMATIC_CHECKS:
        passed = sum(1 for record in records if record["checks"].get(check))
        print(rate_line(check, passed, len(records)))

    latencies = sorted(record["latency_ms"] for record in records)
    if latencies:
        p50 = latencies[len(latencies) // 2]
        p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))]
        print(f"\n  latency                  p50 {p50}ms   p95 {p95}ms")

    if not labels:
        print("\nno human labels yet: uv run python -m evals.label "
              f"--tag {args.tag}")
        return

    # --- layer 2: human labels -----------------------------------
    # Non-answers are excluded from the rate and reported separately,
    # because they mean two different things: many "unsure" on a criterion
    # is a rubric problem, many "unqualified" is a coverage problem that
    # says nothing about the model. Lumping them together would send you
    # off rewriting a criterion that was fine.
    print("\nHUMAN LABELS (rates over decided answers only)")
    for criterion in CRITERIA:
        answers = [label["labels"].get(criterion["key"]) for label in labels.values()]
        decided = [answer for answer in answers if answer in (True, False)]
        unsure = sum(1 for answer in answers if answer is None)
        unqualified = sum(1 for answer in answers if answer == UNQUALIFIED)
        flags = []
        if unsure:
            flags.append(f"{unsure} unsure")
        if unqualified:
            flags.append(f"{unqualified} above level")
        line = rate_line(criterion["key"], sum(decided), len(decided))
        print(line + (f"   ({', '.join(flags)})" if flags else ""))

    # Only items where every criterion got a real answer can be called a
    # clean pass; anything else would silently count a non-answer as a fail.
    covered = [
        label for label in labels.values()
        if all(label["labels"].get(c["key"]) in (True, False) for c in CRITERIA)
    ]
    fully_ok = sum(
        1 for label in covered
        if all(label["labels"][c["key"]] is True for c in CRITERIA)
    )
    print("\n" + rate_line("ALL criteria pass", fully_ok, len(covered)))
    if len(covered) < len(labels):
        print(f"  {len(labels) - len(covered)} of {len(labels)} items excluded: "
              "not every criterion was decided")

    # --- per-slice: qualitative only ------------------------------
    # 4-5 items per slice. These counts point you at where to look; they
    # are not measurements and should never be quoted as percentages.
    print("\nPER SLICE (qualitative — too few items per slice for rates)")
    by_slice: dict[str, list[int]] = defaultdict(list)
    for record in records:
        label = labels.get(record["id"])
        if label:
            failures = sum(1 for c in CRITERIA if label["labels"].get(c["key"]) is False)
            by_slice[record["slice"]].append(failures)
    for slice_name in sorted(by_slice):
        failures = by_slice[slice_name]
        clean = sum(1 for count in failures if count == 0)
        print(f"  {slice_name:<12} {clean}/{len(failures)} items with zero failures, "
              f"{sum(failures)} failed criteria total")

    # --- the actual error analysis --------------------------------
    print("\nFAILURES (this is the part worth reading)")
    for record in records:
        label = labels.get(record["id"])
        if not label:
            continue
        failed = [c["key"] for c in CRITERIA if label["labels"].get(c["key"]) is False]
        if not failed:
            continue
        print(f"\n  {record['id']} {record['word']} ({record['slice']}, {record['level']})")
        print(f"    failed: {', '.join(failed)}")
        if record["parsed"]:
            print(f"    sentence: {record['parsed'].get('sentence')}")
        if label.get("note"):
            print(f"    note: {label['note']}")


if __name__ == "__main__":
    main()
