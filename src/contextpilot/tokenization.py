"""Explicit encoding counts for plain text; not complete model-request accounting."""

ENCODINGS = ("o200k_base", "cl100k_base", "p50k_base")


def counter(encoding):
    if encoding not in ENCODINGS:
        raise ValueError("Choose an explicit supported encoding: " + ", ".join(ENCODINGS))
    try:
        import tiktoken
    except ImportError as e:
        raise ValueError(
            'Tokenizer extra is missing. Install with: python -m pip install tiktoken==0.12.0 (or ".[tokenizer]" from the checkout).'
        ) from e
    try:
        codec = tiktoken.get_encoding(encoding)
    except Exception as e:
        raise ValueError(
            "Encoding assets unavailable. tiktoken may need a one-time download; provision its cache or retry online."
        ) from e
    return lambda text: len(codec.encode(text, disallowed_special=()))


def measurement(text, encoding):
    count = counter(encoding)
    return {
        "encoding": encoding,
        "textTokens": count(text),
        "scope": "Exact for this text and selected encoding only; excludes request wrappers, tools, reasoning, outputs and Codex usage accounting.",
    }
