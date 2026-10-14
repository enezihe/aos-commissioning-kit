"""Remove secrets from text before it leaves this computer.

Patterns catch the usual shapes (keys, tokens, passwords written as name=value, e-mail
addresses). This is a safety net, not a guarantee: always look at what will be sent
(`triage` without --send prints it) before sending logs from a real customer.
"""
import re
from collections import Counter
from typing import Counter as CounterType, Tuple

PLACEHOLDER = "<redacted>"

_WHOLE = [
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)),
    ("anthropic key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}")),
    ("openshift token", re.compile(r"sha256~[A-Za-z0-9_\-]{20,}")),
    ("github token", re.compile(r"\b(?:ghp|gho|ghs|ghu)_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}")),
    ("aws key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}")),
    ("bearer token", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=\-]{16,}")),
    ("email address", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
]

# name = value, where the name suggests a secret. The name is kept, the value is replaced.
_ASSIGNMENT = re.compile(
    r"(?i)\b([A-Za-z0-9_.\-]*(?:password|passwd|secret|token|api[_-]?key|credential)[A-Za-z0-9_.\-]*)"
    r"(\s*[:=]\s*)(['\"]?)([^\s'\",;]{4,})\3"
)


def redact(text: str) -> Tuple[str, CounterType]:
    """Return the cleaned text and how many items of each kind were replaced."""
    found: CounterType = Counter()

    for kind, pattern in _WHOLE:
        text, n = pattern.subn(PLACEHOLDER, text)
        if n:
            found[kind] += n

    def assignment(match: "re.Match") -> str:
        name, sep, quote, value = match.groups()
        if value == PLACEHOLDER or value.isdigit():       # already clean, or a plain number
            return match.group(0)
        found["secret assignment"] += 1
        return f"{name}{sep}{quote}{PLACEHOLDER}{quote}"

    text = _ASSIGNMENT.sub(assignment, text)
    return text, found
