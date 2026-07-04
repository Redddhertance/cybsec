# stage 6 - pii scrub via spacy ner.
# regex (stage 5) only gets structured ids. names of ppl/places/orgs have no fixed shape so
# spacy's statistical ner tokenises the (already regex-scrubbed) sentence + labels entities.
# configured labels (PERSON, GPE, LOC, ORG by default) get swapped for reversible placeholders
# in the same RedactionMap.
# model's loaded once at startup + reused. spans replaced back-to-front so the earlier char
# offsets stay valid while we sub.

from __future__ import annotations

from gateway.config import Settings
from gateway.redaction import RedactionMap


class NerScrubber:
    def __init__(self, settings: Settings) -> None:
        import spacy  # lazy import so tests can stub this stage

        # only need the ner bits, disable the rest for speed
        self._nlp = spacy.load(settings.spacy_model, disable=["lemmatizer", "textcat"])
        self._labels = set(settings.ner_labels)

    def scrub(self, text: str, rmap: RedactionMap) -> str:
        doc = self._nlp(text)
        spans = [ent for ent in doc.ents if ent.label_ in self._labels]
        if not spans:
            return text
        # go back-to-front so start/end char offsets stay put
        for ent in sorted(spans, key=lambda e: e.start_char, reverse=True):
            placeholder = rmap.placeholder_for(ent.label_, ent.text)
            text = text[: ent.start_char] + placeholder + text[ent.end_char :]
        return text
