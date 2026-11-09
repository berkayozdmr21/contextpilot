"""Self-contained, escaped HTML report. No remote fonts, scripts, or requests."""

import html
import json


def html_report(data):
    esc = lambda value: html.escape(str(value), quote=True)
    selected = data.get("selected", [])
    tokenizer = data.get("tokenization")
    cards = [
        ("OUTPUT CHARACTERS", data.get("outputChars", 0)),
        ("SELECTED FILES", len(selected)),
        ("ELIGIBLE FILES", data.get("eligibleFiles", 0)),
        (
            "TEXT REDUCTION / SELECTED FILES",
            str(data.get("reductionVsSelectedFilesPct", "—")) + "%",
        ),
    ]
    if tokenizer:
        cards[2] = ("TEXT TOKENS / " + tokenizer["encoding"], tokenizer["textTokens"])
        cards[3] = (
            "TOKEN REDUCTION / SELECTED FILES",
            str(tokenizer["reductionVsSelectedFilesPct"]) + "%",
        )
    tiles = "".join(
        "<article><small>" + esc(k) + "</small><strong>" + esc(v) + "</strong></article>"
        for k, v in cards
    )
    rows = "".join(
        "<tr><td>"
        + esc(r["path"])
        + "</td><td>"
        + esc(r["score"])
        + "</td><td>"
        + esc(", ".join(r["matched"]))
        + "</td></tr>"
        for r in selected
    )
    payload = html.escape(json.dumps(data, ensure_ascii=False, indent=2))
    return (
        """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>ContextPilot / Context report</title><style>
*{box-sizing:border-box}body{margin:0;background:#f3f1e9;color:#293b36;font:15px system-ui,sans-serif}main{max-width:1100px;margin:auto;padding:45px 25px}header{display:flex;justify-content:space-between;border-bottom:1px solid #ccd0c4;padding-bottom:20px;font-weight:700;letter-spacing:-.6px}.tag{font:10px monospace;letter-spacing:2px;color:#6b7c6f}h1{font:normal 64px Georgia,serif;letter-spacing:-3px;margin:60px 0 20px}h1 i{color:#a8593f}.query{font:20px monospace;overflow-wrap:anywhere;line-height:1.6}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:35px 0}article{border:1px solid #cdd2c5;padding:22px;background:#faf9f2}small{font-size:9px;letter-spacing:1px;display:block;color:#6d796f}strong{font-size:32px;display:block;margin-top:15px;font-weight:500}.note{padding:20px;border-left:3px solid #a8593f;background:#ece8dc;line-height:1.8}h2{margin-top:40px;font-size:18px}table{border-collapse:collapse;width:100%;font-size:12px}td,th{text-align:left;padding:15px 8px;border-bottom:1px solid #d4d8ca;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#e7eade;padding:20px;font-size:11px;line-height:1.7}footer{border-top:1px solid #ccd0c4;margin-top:40px;padding-top:20px;font-size:11px;color:#758273}@media(max-width:700px){.cards{grid-template-columns:1fr 1fr}h1{font-size:43px}td{padding:10px 4px}main{padding:25px 16px}}
</style><main><header><span>◧ contextpilot</span><span class="tag">LOCAL / MEASURABLE / OPEN SOURCE</span></header>
<h1>Less noise.<br><i>More useful context.</i></h1><p class="tag">QUERY</p><p class="query">"""
        + esc(data.get("query", ""))
        + """</p><section class="cards">"""
        + tiles
        + """</section>
<p class="note">This report measures extracted text size and, when explicitly selected, plain-text encoding tokens. It does not measure Codex quota, full model-request tokens, reasoning cost or solution quality. Negative reduction means the labelled excerpt was larger than the baseline. Dependency discovery is bounded and may miss connections. Session references require the acknowledged baseline in the same chat.</p>
<h2>Selection evidence</h2><table><thead><tr><th>File</th><th>Score</th><th>Matched terms</th></tr></thead><tbody>"""
        + rows
        + """</tbody></table>
<h2>Reproducible report</h2><details><summary>View complete JSON</summary><pre>"""
        + payload
        + """</pre></details><footer>ContextPilot · No API key. No telemetry. No quota bypass.</footer></main></html>"""
    )
