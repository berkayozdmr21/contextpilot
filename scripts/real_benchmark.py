"""Evaluate against this tool's real source, isolated from README/benchmark labels."""
import json
import shutil
import sys
import tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'src'))
from contextpilot.engine import pack

cases=[('source-budget','pack max_chars per_file selected','contextpilot/engine.py','def pack('),
       ('redact-secrets','redact SECRETS PRIVATE KEY','contextpilot/safety.py','def redact('),
       ('log-evidence','digest_log error anchors repeated','contextpilot/logs.py','def digest_log('),
       ('checkpoint-resume','checkpoint recall snapshot changes','contextpilot/memory.py','def checkpoint('),
       ('html-escaping','html_report escape Content Security Policy','contextpilot/report.py','def html_report(')]
results=[]
with tempfile.TemporaryDirectory(prefix='contextpilot-real-') as directory:
    corpus=Path(directory)
    shutil.copytree(root/'src/contextpilot',corpus/'contextpilot',ignore=shutil.ignore_patterns('__pycache__','benchmark.py'))
    for name,query,path,marker in cases:
        output,report=pack(corpus,query,4500,3)
        results.append({'case':name,'expectedFile':path,
                        'evidenceFound':path in {s['path'] for s in report['selected']} and marker in output,
                        'outputChars':report['outputChars'],'selectedFullFileChars':report['selectedFullFileChars'],
                        'reductionVsSelectedFilesPct':report['reductionVsSelectedFilesPct']})
data={'dataset':'ContextPilot actual Python source; excludes synthetic benchmark generator and docs',
      'methodology':'Five manually labelled source-location tasks; tests excerpt retrieval, not coding success.',
      'cases':results,'limitations':'Self-retrieval on a small project. Lexical query wording favors identifiers. No model usage measured.'}
destination=root/'examples/results/real-source.json';destination.parent.mkdir(exist_ok=True,parents=True)
destination.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
print(json.dumps(data,indent=2))
if not all(r['evidenceFound'] for r in results):raise SystemExit('Real source evidence check failed')
