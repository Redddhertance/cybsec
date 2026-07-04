# stage 8 - egress filtering. two jobs on the provider's response, in order:
#   1. re-run aho-corasick vs the internal-leak sig set. catches secrets / internal data
#      that should never go back to a client -> block on a hit.
#   2. un-redact: swap the placeholder tokens back to the user's real pii via the per-req
#      RedactionMap so the client gets a coherent answer, while the real values never
#      actually reached the provider.
# un-redact runs after the scan so the scan sees exactly what the model spat out.

from __future__ import annotations

from gateway.redaction import RedactionMap
from gateway.stages import StageError
from gateway.stages.threatscan import ThreatScanner

_STAGE = "egress"


def filter_response(text: str, rmap: RedactionMap, internal_scanner: ThreatScanner) -> str:
    # scan the llm output for internal-data leaks, then restore pii
    leaks = internal_scanner.matches(text)
    if leaks:
        raise StageError(
            _STAGE,
            502,
            "Response blocked: potential internal-data leak detected.",
        )
    return rmap.unredact(text)
