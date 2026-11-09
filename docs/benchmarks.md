# Measurement protocol

## What is measured

Character counts of normalized, best-effort-redacted source text and the labelled output packet. Counts include headers, line labels and warnings. A lower count means less text was prepared; it is not a measurement of Codex allowance, elapsed coding time, exact model tokens or task success.

## Actual-source dataset

The evaluator copies `src/contextpilot/*.py` to an isolated directory, excluding `benchmark.py` and bytecode. README files, documentation and benchmark labels are not in the corpus. Five manually specified queries must retrieve the expected file and the declaration of its named function. Queries intentionally include useful identifiers; they do not test semantic understanding or cross-language translation.

Budget: 4,500 characters; at most three selected files. Baseline: complete text of files selected by the same run.

| Task | Selected full files, chars | Packet, chars | Text reduction | Required declaration |
|---|---:|---:|---:|---|
| source-budget | 14,635 | 4,137 | 71.73% | Found |
| redact-secrets | 15,143 | 4,204 | 72.24% | Found |
| log-evidence | 14,635 | 4,177 | 71.46% | Found |
| checkpoint-resume | 6,106 | 3,680 | 39.73% | Found |
| html-escaping | 12,285 | 4,002 | 67.42% | Found |

These are small-project self-retrieval results, not a representative industry dataset. An early run missed the redaction function because dense regex literals crowded it out. Declaration weighting and separated windows addressed that observed failure, with a regression test. This does not eliminate other retrieval misses.

## Synthetic ShopCore dataset

Thirty deterministically generated Python source files: ten task-related modules and twenty catalog distractors. Each of five queries has two expected file / function markers. Relevant modules deliberately contain repeated background comments around the target function. This makes excerpt selection easy and produces large reductions; it is useful as a regression fixture, not as typical savings evidence.

All ten labelled markers must remain present. The generated packet is capped at 4,500 characters and four files. `eligibleSourceChars` is a whole-corpus baseline; `selectedFullFileChars` is the narrower selected-file baseline. Both are reported. A result can be negative if the labels make a packet longer than a tiny original file.

## Noisy-log dataset

2,003 deterministic lines: repeated heartbeat messages, one UploadOffset failure, a source location and an AssertionError. Required evidence must remain in the digest. This fixture is intentionally repetitive and is not representative of every production log. The raw string is generated in `src/contextpilot/benchmark.py`; the digest is checked into `examples/results/log-digest.md`.

## Reproduce

```sh
python -m pip install .
python scripts/benchmark.py --output examples/results
python scripts/real_benchmark.py
python scripts/render_assets.py
```

Synthetic results are checked for deterministic regeneration in CI on Windows and Linux. Real-source results naturally change when the implementation changes. The report excludes local absolute paths and elapsed wall-clock timing.

## Quality gates

- Unit / integration tests exercise 34 behavior cases. Linux additionally runs symlink cases that Windows may skip due to account privileges.
- A case with missing required evidence fails even when output is smaller.
- Character budget violations fail.
- Same-size / same-mtime source changes must not return stale cached text.
- Installer must work without the source checkout and must refuse overwriting an existing destination.
- HTML must escape input; known secret patterns must not appear in pack output or the index.

## What remains unmeasured

Actual Codex subscription usage; exact tokenizer counts; reasoning tokens; prompt-cache behavior; multi-turn follow-up costs; correctness of a completed bug fix; effects on large multilingual or generated-code repositories. A useful future study would run paired agent tasks, check correctness with hidden tests and record total usage across the whole task. That experiment is not part of the present results.
