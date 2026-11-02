"""Header lexicon: split a column header into terms and resolve them.

Vocabulary lives in vocab/*.yaml (canonical term -> aliases). Adding terms is
a data change. Resolution is pure and deterministic.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

VOCAB_DIR = Path(__file__).parent / "vocab"
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_NON_ALNUM = re.compile(r"[^A-Za-z0-9]+")


def split_header(header: str) -> tuple[str, ...]:
    """Split on separators and camel/Pascal case; lowercase every term."""
    spaced = _CAMEL.sub(" ", header)
    return tuple(t.lower() for t in _NON_ALNUM.split(spaced) if t)


@dataclass(frozen=True)
class HeaderResolution:
    """Result of resolving one header against the lexicon."""

    terms: tuple[str, ...]
    unresolved: tuple[str, ...]
    resolved: bool

    @property
    def phrase(self) -> str:
        """Canonical terms joined into a phrase, e.g. 'gross revenue'."""
        return " ".join(self.terms)


@dataclass(frozen=True)
class Lexicon:
    """Maps every known word (canonical or alias) to its canonical term."""

    canonical: Mapping[str, str] = field(repr=False)

    @classmethod
    def from_entries(cls, entries: Mapping[str, Sequence[str]]) -> Lexicon:
        """Build from {canonical: [aliases]}; a word may have only one owner."""
        owners: dict[str, str] = {}
        for term in sorted(entries):
            for word in (term, *sorted(entries[term])):
                key = word.lower()
                owner = owners.setdefault(key, term.lower())
                if owner != term.lower():
                    raise ValueError(
                        f"term {key!r} maps to both {owner!r} and {term.lower()!r}"
                    )
        return cls(owners)

    def resolve(self, header: str) -> HeaderResolution:
        """Resolve each term of a header; resolved only if all terms are known."""
        tokens = split_header(header)
        terms = tuple(self.canonical[t] for t in tokens if t in self.canonical)
        unresolved = tuple(t for t in tokens if t not in self.canonical)
        return HeaderResolution(terms, unresolved, bool(tokens) and not unresolved)


@lru_cache(maxsize=1)
def load_lexicon() -> Lexicon:
    """Load and merge every vocab file, sorted by file name."""
    merged: dict[str, list[str]] = {}
    for path in sorted(VOCAB_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        for term, aliases in data["terms"].items():
            merged.setdefault(term, []).extend(aliases)
    return Lexicon.from_entries(merged)
