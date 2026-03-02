"""Inter-annotator agreement for the labelled ground-truth corpus.

A supervised quality model is only as good as its labels, so the corpus needs
its own acceptance gate. This module implements observed agreement and Cohen's
kappa, the chance-corrected statistic introduced in Cohen (1960), together with
the threshold check the project uses before a labelling round is accepted.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "DEFAULT_THRESHOLD",
    "AgreementError",
    "AgreementReport",
    "cohens_kappa",
    "confusion_matrix",
    "observed_agreement",
    "score_agreement",
]

#: Minimum kappa at which a labelling round is accepted for training.
DEFAULT_THRESHOLD = 0.70


class AgreementError(ValueError):
    """Raised when agreement cannot be computed from the inputs given."""


def _validate(a: Sequence[str], b: Sequence[str]) -> None:
    if len(a) != len(b):
        raise AgreementError(f"unequal lengths: {len(a)} and {len(b)}")
    if not a:
        raise AgreementError("cannot compute agreement over an empty sample")


def observed_agreement(a: Sequence[str], b: Sequence[str]) -> float:
    """Share of items on which the two annotators chose the same label."""
    _validate(a, b)
    return sum(1 for x, y in zip(a, b, strict=True) if x == y) / len(a)


def cohens_kappa(a: Sequence[str], b: Sequence[str]) -> float:
    """Cohen's kappa for two annotators over a shared set of items.

    Kappa corrects observed agreement for the agreement expected by chance:
    ``(p_o - p_e) / (1 - p_e)``. It is 1.0 for perfect agreement, 0.0 for
    chance-level agreement and negative when annotators disagree more than
    chance would predict.

    When both annotators assign exactly one label to everything, expected
    agreement is 1.0 and kappa is undefined. The convention here is to return
    1.0 for identical constant labelling and 0.0 otherwise, which is the
    behaviour that keeps a degenerate corpus from passing the gate by accident.
    """
    _validate(a, b)
    n = len(a)
    p_o = observed_agreement(a, b)

    counts_a = Counter(a)
    counts_b = Counter(b)
    labels = set(counts_a) | set(counts_b)
    p_e = sum((counts_a[label] / n) * (counts_b[label] / n) for label in labels)

    if p_e >= 1.0:
        return 1.0 if p_o >= 1.0 else 0.0
    return (p_o - p_e) / (1.0 - p_e)


def confusion_matrix(a: Sequence[str], b: Sequence[str]) -> dict[tuple[str, str], int]:
    """Counts of every (annotator A label, annotator B label) pair."""
    _validate(a, b)
    return dict(Counter(zip(a, b, strict=True)))


@dataclass(frozen=True, slots=True)
class AgreementReport:
    """Result of scoring one labelling round."""

    items: int
    labels: tuple[str, ...]
    observed_agreement: float
    kappa: float
    threshold: float

    @property
    def passed(self) -> bool:
        """Whether the round clears the acceptance threshold."""
        return self.kappa >= self.threshold

    @property
    def interpretation(self) -> str:
        """Landis and Koch (1977) descriptive band for the kappa value."""
        k = self.kappa
        if k < 0.00:
            return "poor"
        if k < 0.21:
            return "slight"
        if k < 0.41:
            return "fair"
        if k < 0.61:
            return "moderate"
        if k < 0.81:
            return "substantial"
        return "almost perfect"

    def summary(self) -> str:
        verdict = "ACCEPTED" if self.passed else "REJECTED"
        return (
            f"{verdict}: kappa {self.kappa:.3f} ({self.interpretation}), "
            f"observed agreement {self.observed_agreement:.1%}, "
            f"{self.items} items, threshold {self.threshold:.2f}"
        )


def score_agreement(
    a: Sequence[str],
    b: Sequence[str],
    *,
    threshold: float = DEFAULT_THRESHOLD,
) -> AgreementReport:
    """Score a labelling round against the acceptance threshold."""
    _validate(a, b)
    return AgreementReport(
        items=len(a),
        labels=tuple(sorted(set(a) | set(b))),
        observed_agreement=observed_agreement(a, b),
        kappa=cohens_kappa(a, b),
        threshold=threshold,
    )
