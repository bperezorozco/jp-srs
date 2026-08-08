"""Hand-label the outputs of a run. This is the anchor for everything else.

Human labels are the ground truth the LLM judge gets measured against. No
amount of judge engineering substitutes for one person looking at their own
system's outputs — that is also where the real failure taxonomy comes from,
which is why every item ends with a free-text note.

Two deliberate design choices:

  * The layer 1 automatic checks are NOT shown while labelling. Showing a
    machine verdict to an annotator anchors them to it, and then the
    agreement you measure later is partly agreement with yourself.

  * Every criterion accepts two kinds of non-answer, and they mean
    different things. "unsure" means the annotator understood the item and
    still could not decide, which points at a badly written criterion.
    "unqualified" means the item is above the annotator's Japanese level,
    which is a coverage limit and says nothing about the rubric. Collapsing
    the two would make a rubric look broken when the real problem was
    expertise, or vice versa.

    Guessing instead of answering 'x' is the worst option available: it
    does not produce noisy labels, it produces systematically wrong ones,
    and a judge validated against them will happily reproduce the mistakes
    and report a high agreement.

Progress is appended after each item, so quitting never loses work, and
rerunning resumes where you stopped.

Usage:
    uv run python -m evals.label --tag baseline
"""

import argparse
import json
from pathlib import Path

from evals.rubric import CRITERIA, UNQUALIFIED

RESULTS_DIR = Path(__file__).parent / "results"

ANSWERS = {"y": True, "n": False, "u": None, "x": UNQUALIFIED}


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def show(record: dict) -> None:
    """Print one generated output for review."""
    kind = "kanji" if record["is_kanji"] else "word"
    print("\n" + "=" * 68)
    print(f"{record['id']}  {kind}: {record['word']}   "
          f"level: {record['level']}   language: {record['language']}   "
          f"slice: {record['slice']}")
    print("=" * 68)

    if record["error"]:
        print(f"\n  !! generation failed: {record['error']}")
        if record["raw"]:
            print(f"  raw output: {record['raw'][:400]}")
        return

    parsed = record["parsed"]
    print(f"\n  sentence     {parsed.get('sentence')}")
    print(f"  furigana     {parsed.get('furigana')}")
    print(f"  translation  {parsed.get('translation')}")
    print(f"  note         {parsed.get('note')}")


def ask(question: str) -> bool | None | str:
    """Ask one criterion. Returns a label value, or 'quit'/'skip'."""
    while True:
        answer = input(
            f"  {question}\n    [y/n | u=unsure | x=above my level | s=skip item | q=quit] "
        ).strip().lower()
        if answer in ANSWERS:
            return ANSWERS[answer]
        if answer in ("s", "q"):
            return "skip" if answer == "s" else "quit"
        print("    -> answer y, n, u, x, s or q")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default="baseline", help="run identifier to label")
    args = parser.parse_args()

    run_path = RESULTS_DIR / f"run-{args.tag}.jsonl"
    labels_path = RESULTS_DIR / f"labels-{args.tag}.jsonl"
    if not run_path.exists():
        raise SystemExit(f"{run_path} not found. Run evals.run first.")

    records = load_jsonl(run_path)
    already_labelled = {label["id"] for label in load_jsonl(labels_path)}
    pending = [record for record in records if record["id"] not in already_labelled]

    if not pending:
        print(f"all {len(records)} items already labelled in {labels_path}")
        return

    print(f"{len(pending)} items to label ({len(already_labelled)} already done).")
    print("Judge each criterion independently — a sentence can sound natural")
    print("and still have the wrong readings.")
    print("  u  understood it, still cannot decide  -> the criterion is unclear")
    print("  x  above my Japanese level             -> coverage limit, never a guess")

    with labels_path.open("a", encoding="utf-8") as handle:
        for record in pending:
            show(record)
            print()

            labels, aborted = {}, None
            for criterion in CRITERIA:
                answer = ask(criterion["short"])
                if answer in ("quit", "skip"):
                    aborted = answer
                    break
                labels[criterion["key"]] = answer

            if aborted == "quit":
                print("\nstopped. Rerun the same command to carry on.")
                break
            if aborted == "skip":
                print("  item skipped, not recorded.")
                continue

            note = input("\n  what went wrong / worth noting? (enter to skip) ").strip()
            handle.write(json.dumps(
                {"id": record["id"], "labels": labels, "note": note or None},
                ensure_ascii=False,
            ) + "\n")
            handle.flush()

    print(f"\nlabels in {labels_path}")
    print(f"next: uv run python -m evals.report --tag {args.tag}")


if __name__ == "__main__":
    main()
