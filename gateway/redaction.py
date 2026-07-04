# reversible pii redaction bookkeeping, shared by stages 5, 6 and 8.
# plain [EMAIL] tokens cant be reversed, so every scrubbed value gets a unique indexed
# placeholder ([EMAIL_1], [PERSON_2]...). the placeholder->original map is kept per-req in a
# RedactionMap and the real value never leaves the gateway. egress swaps the tokens back so
# the client still gets a coherent answer.
# same value -> same placeholder, so a phone no. said twice collapses to one token + reverses clean.

from __future__ import annotations

import re
from collections import Counter


class RedactionMap:
    def __init__(self) -> None:
        # placeholder -> original value
        self._to_original: dict[str, str] = {}
        # (label, original) -> placeholder, for dedup
        self._dedup: dict[tuple[str, str], str] = {}
        # per-label running index for the numbering
        self._counter: Counter[str] = Counter()

    def placeholder_for(self, label: str, value: str) -> str:
        # stable placeholder for value under label. label = upper tag eg EMAIL/PERSON.
        # repeats map to the same token.
        key = (label, value)
        existing = self._dedup.get(key)
        if existing is not None:
            return existing
        self._counter[label] += 1
        placeholder = f"[{label}_{self._counter[label]}]"
        self._dedup[key] = placeholder
        self._to_original[placeholder] = value
        return placeholder

    def unredact(self, text: str) -> str:
        # swap every known placeholder back to its original
        if not self._to_original:
            return text
        # longest first so [EMAIL_10] doesnt get clobbered by [EMAIL_1]
        keys = sorted(self._to_original, key=len, reverse=True)
        pattern = re.compile("|".join(re.escape(k) for k in keys))
        return pattern.sub(lambda m: self._to_original[m.group(0)], text)

    def counts_by_type(self) -> dict[str, int]:
        # distinct placeholders per label, for the audit log
        return dict(self._counter)

    @property
    def total(self) -> int:
        return len(self._to_original)
