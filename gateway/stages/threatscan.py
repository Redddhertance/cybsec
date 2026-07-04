# stage 4 (ingress) + part of stage 8 (egress) - aho-corasick threat scan.
# wraps the compiled c++ ac_engine.Scanner. at ingress the prompt gets matched vs thousands
# of known injection sigs, any hit = 403. same thing reused at egress vs a separate
# internal-leak sig set.
# sig files are json: either a flat list of strings, or an obj whose values are lists of
# strings grouped by category. a pattern's spot in the flattened list is its id, `names`
# maps ids back to readable labels for the logs.

from __future__ import annotations

import json
from pathlib import Path

import ac_engine

from gateway.stages import StageError

_STAGE = "threatscan"


def _load_signatures(path: Path) -> tuple[list[str], list[str]]:
    # returns (patterns, names). handles a flat list or a category->list map.
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    patterns: list[str] = []
    names: list[str] = []
    if isinstance(raw, dict):
        for category, items in raw.items():
            # skip doc keys (eg "_comment") + anything thats not a list
            if category.startswith("_") or not isinstance(items, list):
                continue
            for item in items:
                patterns.append(item)
                names.append(f"{category}:{item}")
    elif isinstance(raw, list):
        for item in raw:
            patterns.append(item)
            names.append(item)
    else:
        raise ValueError(f"Unsupported signature file shape in {path!r}")
    return patterns, names


class ThreatScanner:
    # a built ac scanner + the readable sig names alongside

    def __init__(self, patterns: list[str], names: list[str]) -> None:
        self._scanner = ac_engine.Scanner(patterns)
        self._names = names

    @classmethod
    def from_file(cls, path: Path) -> "ThreatScanner":
        patterns, names = _load_signatures(path)
        return cls(patterns, names)

    @property
    def pattern_count(self) -> int:
        return self._scanner.pattern_count

    def matches(self, text: str) -> list[str]:
        # distinct sig names found in text
        hits = self._scanner.scan(text)
        seen: dict[int, str] = {}
        for pattern_id, _start, _end in hits:
            seen.setdefault(pattern_id, self._names[pattern_id])
        return list(seen.values())


def scan_ingress(text: str, scanner: ThreatScanner) -> None:
    # 403 the req if any injection sig matches the prompt
    hits = scanner.matches(text)
    if hits:
        # keep the detail vague to the client, real hits go to the audit log
        raise StageError(
            _STAGE,
            403,
            "Request blocked: prohibited content detected.",
            headers={},
        )
