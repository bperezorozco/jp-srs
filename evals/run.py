"""Run the golden set through the real jp-srs generation pipeline.

Two things this file is careful about, both of which matter more than the
code itself:

  1. It evaluates the SYSTEM, not the model. It imports build_system,
     build_prompt, parse_response and generate straight out of src.main
     rather than reimplementing them. A reimplemented prompt drifts from
     the real one within weeks, and then the eval measures a system that
     does not exist.

  2. It records provenance. Model, prompt fingerprint, dataset version and
     timestamp all get stored alongside the outputs. Without that, a
     regression six weeks from now is unattributable: you cannot tell a
     prompt change from a model change from a dataset change.

Runs are immutable artefacts: the script refuses to overwrite an existing
tag. Rerunning is fine, overwriting history is not.

Usage:
    uv run python -m evals.run --tag baseline
    uv run python -m evals.run --tag smoke --limit 3
"""

import argparse
import asyncio
import hashlib
import inspect
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from src import main as app
from evals.dataset import GOLDEN_SET, DATASET_VERSION
from evals.rubric import automatic_checks

RESULTS_DIR = Path(__file__).parent / "results"


def prompt_fingerprint() -> str:
    """Short hash of the prompt-building code.

    Provenance, not security. It lets a stored run state which version of
    the prompt produced it, so a later regression can be traced to a prompt
    edit rather than blamed on the model.
    """
    source = inspect.getsource(app.build_system) + inspect.getsource(app.build_prompt)
    return hashlib.sha256(source.encode()).hexdigest()[:12]


async def run_item(item: dict) -> dict:
    """Generate one sentence and apply the layer 1 checks to it."""
    system = app.build_system(item["level"])
    prompt = app.build_prompt(item["word"], item["language"], item["is_kanji"])

    raw, parsed, error = None, None, None
    started = time.monotonic()
    try:
        raw = await app.generate(prompt, system)
        parsed = app.parse_response(raw)
    except Exception as exc:
        # A failed item is a result, not a crash: format failures are one of
        # the things we are measuring, so they belong in the output file.
        error = f"{type(exc).__name__}: {exc}"
    latency_ms = round((time.monotonic() - started) * 1000)

    return {
        **item,
        "raw": raw,
        "parsed": parsed,
        "error": error,
        "latency_ms": latency_ms,
        "checks": automatic_checks(item, parsed),
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default="baseline", help="run identifier")
    parser.add_argument("--limit", type=int, help="only run the first N items")
    args = parser.parse_args()

    out_path = RESULTS_DIR / f"run-{args.tag}.jsonl"
    meta_path = RESULTS_DIR / f"run-{args.tag}.meta.json"
    if out_path.exists():
        raise SystemExit(
            f"{out_path} already exists. Runs are immutable — pick another --tag."
        )
    RESULTS_DIR.mkdir(exist_ok=True)

    items = GOLDEN_SET[: args.limit] if args.limit else GOLDEN_SET

    meta = {
        "tag": args.tag,
        "dataset_version": DATASET_VERSION,
        "n_items": len(items),
        "model": app.MODEL,
        "backend": "api_key" if app.USE_API_KEY else "agent_sdk",
        "prompt_fingerprint": prompt_fingerprint(),
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    print(f"run '{args.tag}': {len(items)} items, model={meta['model']}, "
          f"prompt={meta['prompt_fingerprint']}")

    # Sequential on purpose: generate() wraps a synchronous client, so
    # gathering these would not actually overlap. 20 items is ~90 seconds.
    results = []
    for position, item in enumerate(items, start=1):
        result = await run_item(item)
        results.append(result)
        status = "ERROR" if result["error"] else (
            "ok" if all(result["checks"].values()) else "check-fail"
        )
        print(f"  [{position:>2}/{len(items)}] {item['id']} {item['word']:<6} "
              f"{result['latency_ms']:>5}ms  {status}")

    with out_path.open("w", encoding="utf-8") as handle:
        for result in results:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
    meta["finished_at"] = datetime.now(timezone.utc).isoformat()
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nwrote {out_path}")
    print(f"next: uv run python -m evals.label --tag {args.tag}")


if __name__ == "__main__":
    asyncio.run(main())
