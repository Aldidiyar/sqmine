"""Pseudonymisation and text redaction, applied at the trust boundary.

Direct identifiers are replaced with a keyed HMAC digest. The mapping is
deterministic, so the same customer yields the same reference every time and
episodes can still be linked for churn and repeat-contact analysis, but it
cannot be reversed without the key.

This is pseudonymisation, not anonymisation: under most data-protection
regimes, including the Republic of Kazakhstan's Law No. 94-V, the result is
still personal data and the corresponding obligations still apply.
"""

from __future__ import annotations

import hmac
import re
from hashlib import sha256
from pathlib import Path

__all__ = ["Pseudonymiser", "redact_text"]

_DEFAULT_DIGEST_CHARS = 16

# Order matters, and it is the narrowest pattern first. An email contains
# digits the number rules would otherwise claim; a bare twelve-digit run is far
# more likely a Kazakhstani individual identification number than a telephone
# number, which locally carries eleven digits. The phone rule therefore runs
# last, over whatever the specific rules have not already consumed.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("EMAIL", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("CARD", re.compile(r"(?<!\d)(?:\d[ -]?){15,18}\d(?!\d)")),
    ("ID", re.compile(r"(?<!\d)\d{12}(?!\d)")),
    # Ten digits and up: local numbers are frequently written without the
    # country code, as "701 234 56 78".
    ("PHONE", re.compile(r"(?<!\w)(?:\+?\d[\s\-()]?){9,14}\d(?!\w)")),
)


class Pseudonymiser:
    """Deterministic, keyed replacement of direct identifiers.

    Args:
        key: Secret key. Keep it outside the data store; anyone holding both
            the key and the data can re-identify every subject.
        digest_chars: Length of the hex digest retained. Sixteen hex characters
            give 64 bits, which makes accidental collisions negligible at the
            volumes this package targets.
    """

    def __init__(self, key: bytes, *, digest_chars: int = _DEFAULT_DIGEST_CHARS) -> None:
        if not key:
            raise ValueError("key must not be empty")
        if not 8 <= digest_chars <= 64:
            raise ValueError("digest_chars must be between 8 and 64")
        self._key = key
        self._digest_chars = digest_chars

    @classmethod
    def from_file(cls, path: str | Path, **kwargs: int) -> Pseudonymiser:
        """Load the key from a file, stripping trailing whitespace."""
        data = Path(path).read_bytes().strip()
        if not data:
            raise ValueError(f"key file {path} is empty")
        return cls(data, **kwargs)

    def ref(self, value: str, *, prefix: str = "") -> str:
        """Return a stable pseudonymous reference for ``value``.

        Values are stripped and case-folded first, so ``"AB-1 "`` and ``"ab-1"``
        map to the same reference. Without that, the same customer recorded
        slightly differently in two systems would look like two people.
        """
        if not value or not value.strip():
            raise ValueError("cannot pseudonymise an empty value")
        normalised = value.strip().casefold().encode("utf-8")
        digest = hmac.new(self._key, normalised, sha256).hexdigest()
        return f"{prefix}{digest[: self._digest_chars]}"

    def ref_or_none(self, value: str | None, *, prefix: str = "") -> str | None:
        """Pseudonymise ``value`` unless it is absent."""
        if value is None or not str(value).strip():
            return None
        return self.ref(str(value), prefix=prefix)


def redact_text(text: str | None) -> str | None:
    """Replace identifiers embedded in free text with typed placeholders.

    Field-level pseudonymisation does not help with transcripts, where the
    personal data sits inside the sentence: "my number is 701 234 56 78".
    This performs a conservative pass over the patterns that carry the highest
    risk. It is not a complete solution, and the package does not claim one;
    named-entity redaction is tracked as a known limitation.
    """
    if text is None:
        return None
    redacted = text
    for label, pattern in _PATTERNS:
        redacted = pattern.sub(f"[{label}]", redacted)
    return redacted
