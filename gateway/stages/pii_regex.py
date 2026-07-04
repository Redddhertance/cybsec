# stage 5 - deterministic pii scrub w regex.
# structured ids (emails, phone nos, ssns, cards, ips) have predictable shapes so regex nails
# them precisely before the prompt goes to a 3rd party. each match becomes a reversible
# indexed placeholder in the shared RedactionMap.
# patterns run most-specific first so a card no. doesnt get half-eaten by the phone one.

from __future__ import annotations

import re

from gateway.redaction import RedactionMap

# street-type suffixes, full word + common abbrev
_STREET_TYPES = (
    r"street|st\.?|avenue|ave\.?|road|rd\.?|lane|ln\.?"
    r"|drive|dr\.?|court|ct\.?|place|pl\.?|boulevard|blvd\.?"
    r"|way|row|square|sq\.?|gardens?|terrace|crescent|close|mews|walk"
)

# (label, compiled pattern), run in order
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("CREDIT_CARD", re.compile(r"\b(?:\d[ -]?){13,16}\b")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("IP", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
    (
        "PHONE",
        re.compile(
            r"(?<!\w)(?:\+?\d{1,3}[ .-]?)?(?:\(\d{2,4}\)[ .-]?)?\d{3}[ .-]?\d{3,4}(?!\w)"
        ),
    ),
    # street addresses: "25 Water Street", "1-3 Old Kent Road" etc.
    # needs a leading house no. so bare street names dont get grabbed.
    (
        "ADDRESS",
        re.compile(
            rf"(?<!\w)\d[\d\-–]*\s+[A-Za-z][\w\s]{{1,40}}?\b(?:{_STREET_TYPES})\b",
            re.IGNORECASE,
        ),
    ),
]


def scrub_regex(text: str, rmap: RedactionMap) -> str:
    # text w structured pii swapped out for placeholders
    for label, pattern in _PATTERNS:
        text = pattern.sub(lambda m: rmap.placeholder_for(label, m.group(0)), text)
    return text
