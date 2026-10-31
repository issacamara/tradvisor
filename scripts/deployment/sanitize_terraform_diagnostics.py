"""Redact credential-like content before Terraform diagnostics are emitted."""

from __future__ import annotations

import re
import sys


REDACTIONS = (
    (re.compile(r"(?im)^(\s*authorization\s*:\s*).*$"), r"\1<redacted>"),
    (
        re.compile(
            r"(?i)(authorization[\"']?\s*:\s*[\"']?)(?:Bearer\s+|Basic\s+)?[A-Za-z0-9._~+/=-]+"
        ),
        r"\1<redacted>",
    ),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer <redacted>"),
    (
        re.compile(
            r"(?i)\b(openrouter[_ -]?api[_ -]?key|api[_ -]?key|secret(?:[_ -]?(?:data|value|payload))?|token|password|credential)"
            r"([\"']?\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|[^\s,;]+)"
        ),
        r"\1\2<redacted>",
    ),
    (re.compile(r"(?i)\bsk-or-v1-[A-Za-z0-9_-]+"), "<redacted-openrouter-key>"),
    (re.compile(r"(https?://[^?\s]+)\?[^\s]+"), r"\1?<redacted>"),
)


def sanitize(text: str) -> str:
    for pattern, replacement in REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


if __name__ == "__main__":
    sys.stdout.write(sanitize(sys.stdin.read()))
