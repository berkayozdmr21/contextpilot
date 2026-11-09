# Paired context evidence / 0.2

Same 6,000-character / four-file ceiling. Required labels target the dependency file and its implementation marker. These are small retrieval fixtures, not coding-agent trials.

| Case | Lexical recall | Dependency recall | Lexical text tokens | Dependency text tokens |
|---|---:|---:|---:|---:|
| python-local | 0.0 | 1.0 | 225 | 318 |
| typescript-local | 0.0 | 1.0 | 228 | 328 |
| dart-local | 0.0 | 1.0 | 215 | 308 |
| csharp-local | 0.0 | 1.0 | 218 | 316 |
| known-one-hop-limit | 0.0 | 0.0 | 139 | 232 |

Counts use explicit o200k_base encoding. More evidence can cost more tokens. The known two-hop limitation is deliberately retained.

## Acknowledged same-chat session

| Packet | Characters | Text tokens |
|---|---:|---:|
| Initial full packet | 2214 | 355 |
| Unchanged reference | 558 | 136 |
| Changed unified diff | 1629 | 280 |

The initial complete file must already be retained and explicitly acknowledged in this same chat. A new chat or compaction requires a fresh session and full context. These fixture figures are not total Codex savings.
