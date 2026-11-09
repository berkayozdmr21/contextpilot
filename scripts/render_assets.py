"""Render repository-native SVG figures from checked-in measurement JSON."""
import html
import json
from pathlib import Path
root=Path(__file__).resolve().parents[1]
real=json.loads((root/'examples/results/real-source.json').read_text())
synthetic=json.loads((root/'examples/results/benchmark.json').read_text())
style='<style>text{font-family:Segoe UI,Arial,sans-serif}.mono{font-family:Consolas,monospace}</style>'
hero='''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 420" role="img" aria-label="ContextPilot, local context tools for coding agents">'''+style+'''
<rect width="1200" height="420" rx="14" fill="#eef0e7"/>
<path d="M36 60h1128" stroke="#ced4c4"/><rect x="38" y="26" width="19" height="19" rx="3" fill="#496352"/><path d="M43 36l4 4 6-9" fill="none" stroke="#f5f1df" stroke-width="2"/>
<text x="69" y="42" font-size="19" font-weight="600" fill="#354d40">contextpilot</text>
<text x="1163" y="40" text-anchor="end" class="mono" font-size="10" letter-spacing="2" fill="#72846d">DEVELOPER TOOLS / 01</text>
<text x="42" y="144" font-size="55" font-weight="500" letter-spacing="-2" fill="#2d4437">Less noise.</text>
<text x="42" y="207" font-size="55" font-weight="500" letter-spacing="-2" fill="#a36042">More useful context.</text>
<text x="45" y="252" font-size="16" fill="#6b7f6c">Focused source. Concise failures. Local handoffs.</text>
<rect x="45" y="294" width="98" height="30" rx="15" fill="#dce3d1"/><text x="94" y="314" text-anchor="middle" font-size="10" fill="#425d42">LOCAL FIRST</text>
<rect x="153" y="294" width="135" height="30" rx="15" fill="#dce3d1"/><text x="220" y="314" text-anchor="middle" font-size="10" fill="#425d42">NO MODEL API</text>
<rect x="298" y="294" width="128" height="30" rx="15" fill="#dce3d1"/><text x="362" y="314" text-anchor="middle" font-size="10" fill="#425d42">OPEN SOURCE</text>
<rect x="738" y="105" width="420" height="222" rx="10" fill="#2d4338"/>
<circle cx="758" cy="126" r="4" fill="#bb8367"/><circle cx="773" cy="126" r="4" fill="#a6ac78"/><circle cx="788" cy="126" r="4" fill="#739580"/>
<text x="760" y="167" class="mono" font-size="13" fill="#c3d2bd">$ contextpilot pack "upload offset"</text>
<text x="760" y="204" class="mono" font-size="12" fill="#91af97">01  Discover eligible source</text>
<text x="760" y="234" class="mono" font-size="12" fill="#91af97">02  Rank files + extract evidence</text>
<text x="760" y="264" class="mono" font-size="12" fill="#e7c59c">03  Return a bounded context pack</text>
<path d="M760 286h370" stroke="#516957"/><text x="760" y="309" class="mono" font-size="10" fill="#9db29a">CHARACTER BUDGET · PATHS · LINE NUMBERS</text>
<text x="45" y="388" font-size="10" class="mono" fill="#7d8d75" letter-spacing="1">TEXT PREPARATION, NOT A QUOTA BYPASS.</text></svg>'''
(root/'docs/banner.svg').write_text(hero,encoding='utf-8')
chart=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1100 500" role="img" aria-label="Real source character comparison">',style,
       '<rect width="1100" height="500" rx="10" fill="#f2f1e9"/>',
       '<text x="35" y="42" font-size="22" font-weight="600" fill="#354d40">Actual source. Explicit baselines.</text>',
       '<text x="35" y="68" font-size="12" fill="#76806d">Five labelled source-location tasks · characters, not billing tokens</text>',
       '<rect x="650" y="28" width="12" height="12" fill="#cbd4c0"/><text x="671" y="39" font-size="11" fill="#5c705d">Selected full files</text>',
       '<rect x="860" y="28" width="12" height="12" fill="#a86445"/><text x="881" y="39" font-size="11" fill="#5c705d">Context pack</text>']
maximum=max(r['selectedFullFileChars'] for r in real['cases'])
for i,row in enumerate(real['cases']):
    y=112+i*68
    chart.append('<text x="35" y="{}" font-size="12" fill="#445b48">{}</text>'.format(y+20,html.escape(row['case'])))
    for n,key,color in ((0,'selectedFullFileChars','#cbd4c0'),(1,'outputChars','#a86445')):
        width=row[key]/maximum*610
        chart.append('<rect x="225" y="{}" width="{}" height="16" rx="2" fill="{}"/>'.format(y+n*20,round(width,2),color))
        chart.append('<text x="{}" y="{}" font-size="10" fill="#50634f">{:,}</text>'.format(round(235+width,2),y+n*20+12,row[key]))
    chart.append('<text x="970" y="{}" font-size="19" fill="#a36143">−{}%</text>'.format(y+24,row['reductionVsSelectedFilesPct']))
chart.append('<text x="35" y="478" font-size="11" fill="#7a8270">Evidence checked against named functions. No model was called; equal coding-task quality was not evaluated.</text></svg>')
(root/'docs/benchmark.svg').write_text(''.join(chart),encoding='utf-8')
rows='\n'.join('| {} | {:,} | {:,} | {}% | {} |'.format(r['case'],r['selectedFullFileChars'],r['outputChars'],r['reductionVsSelectedFilesPct'],'Found' if r['evidenceFound'] else 'MISSING') for r in real['cases'])
doc='''# Measurement protocol

## What is measured

Character counts of normalized, best-effort-redacted source text and the labelled output packet. Counts include headers, line labels and warnings. A lower count means less text was prepared; it is not a measurement of Codex allowance, elapsed coding time, exact model tokens or task success.

## Actual-source dataset

The evaluator copies `src/contextpilot/*.py` to an isolated directory, excluding `benchmark.py` and bytecode. README files, documentation and benchmark labels are not in the corpus. Five manually specified queries must retrieve the expected file and the declaration of its named function. Queries intentionally include useful identifiers; they do not test semantic understanding or cross-language translation.

Budget: 4,500 characters; at most three selected files. Baseline: complete text of files selected by the same run.

| Task | Selected full files, chars | Packet, chars | Text reduction | Required declaration |
|---|---:|---:|---:|---|
'''+rows+'''

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
'''
(root/'docs/benchmarks.md').write_text(doc,encoding='utf-8')
print('Rendered banner.svg, benchmark.svg and benchmarks.md from current JSON reports.')

import sys
sys.path.insert(0,str(root/'src'))
from contextpilot.report import html_report
report=json.loads((root/'examples/results/pack-report.json').read_text(encoding='utf-8'))
(root/'examples/results/report.html').write_text(html_report(report),encoding='utf-8')
