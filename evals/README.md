# evals

An evaluation suite for jp-srs sentence generation, built as a hands-on
exercise in LLM evaluation. The system under test is the real one in
`src/main.py`: given a word, a JLPT level and a target language, produce a
JSON object with a sentence, its furigana, a translation and a usage note.

It is a good subject precisely because it is awkward. Quality is
subjective, there is no single correct answer, and a single output can fail
in six independent ways.

## The decision this eval serves

> Is a change to the prompt or the model safe to ship?

Everything below exists to answer that. A metric with no decision attached
is a dashboard, and dashboards do not stop bad deploys.

Ship criteria, written down before running anything so they cannot be
rationalised afterwards:

| Gate | Threshold |
|---|---|
| Automatic checks | 100% — a format failure is a broken card in the app |
| `furigana_ok`, `translation_ok` | no regression vs the baseline run |
| `level_ok` | the weakest criterion; the one worth investing in |
| Latency p95 | guardrail, not a target — under 8s |

## How it is put together

```
dataset.py   frozen golden set, n=20, stratified into slices
rubric.py    layer 1 automatic checks + the 6 judgement criteria
run.py       runs the real pipeline, records provenance -> results/run-<tag>.jsonl
label.py     interactive hand-labelling -> results/labels-<tag>.jsonl
report.py    pass rates with Wilson CIs, per-slice view, failure listing
judge.py     LLM-as-judge over the same rubric                    [block 2]
agreement.py Cohen's kappa, judge vs human                        [block 2]
```

### Three grading layers, cheapest first

1. **Automatic** (`automatic_checks`) — valid JSON, required fields present,
   target word actually appears, furigana contains no kanji. Deterministic,
   free, runs on every commit. Using an LLM judge for any of this would be
   the most common eval antipattern there is.
2. **Human** (`label.py`) — the ground truth. Slow, expensive, irreplaceable.
3. **LLM judge** (`judge.py`) — scales layer 2, and is only trustworthy once
   its agreement with layer 2 has been measured.

### Why the criteria are binary

1–5 scales do not calibrate, in humans or in models: everything collects on
3 and 4, and two annotators will not mean the same thing by "4". Six
independent yes/no questions carry more information and can actually be
agreed upon.

## Running it

```bash
uv run python -m evals.run --tag baseline      # ~90s, generates 20 outputs
uv run python -m evals.label --tag baseline    # ~30 min of your attention
uv run python -m evals.report --tag baseline
```

Runs are immutable: `run.py` refuses to overwrite an existing tag. Labelling
resumes where you left off, so quitting mid-way is safe.

## Things this suite deliberately does

- **Evaluates the system, not the model.** It imports the prompt builders
  from `src.main` instead of copying them, so the eval cannot drift away
  from what production actually sends.
- **Records provenance.** Model, prompt fingerprint, dataset version and
  timestamps, so a future regression can be attributed.
- **Hides the automatic checks from the annotator.** Showing a machine
  verdict during labelling anchors the human to it and quietly corrupts the
  agreement measured later.
- **Treats "unsure" as a signal.** Clustered unsure answers mean the rubric
  is badly written, not that the labeller was careless.
- **Reports confidence intervals.** At n=20 the interval is about ±20
  points. Most apparent improvements at this sample size are noise, and the
  report is built to make that impossible to ignore.
- **Refuses per-slice percentages.** Four items per slice guide where to
  look; they do not measure anything.

## Known limitations

- n=20 detects large effects only. Growing the set is the first upgrade.
- One annotator, so there is no inter-annotator agreement — the human
  labels are an anchor, not an objective truth.
- **The annotator is not N1.** Judgements on advanced items, especially
  readings for rare kanji and naturalness at N2/N1, are marked `x` rather
  than guessed. Coverage therefore varies by criterion, and `level_ok` at
  the top levels is the thinnest. Raising this ceiling means either a more
  advanced annotator or a dictionary-backed check for readings — not a
  better prompt.
- Sampling is non-deterministic and the eval runs once, so run-to-run
  variance is currently unmeasured. Running the same tag three times would
  quantify it.
- The golden set was assembled by hand and reflects assumptions about which
  cases are hard. Real usage logs would be better.
