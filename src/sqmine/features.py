"""Deterministic feature extraction over canonical episodes.

Features are computed from the canonical record only, never from a source
format, so the same code serves every tenant. The function is pure and the
output order is stable, which is what makes a training run reproducible from a
committed configuration.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Any

from sqmine.schema import Episode, Outcome

__all__ = ["FeatureRow", "extract_features", "feature_names", "summarise"]

#: Window within which an earlier episode counts as a repeat contact.
REPEAT_CONTACT_WINDOW = timedelta(days=30)


@dataclass(frozen=True, slots=True)
class FeatureRow:
    """Feature vector for one episode."""

    episode_id: str
    tenant_id: str
    customer_ref: str
    handling_seconds: int
    wait_seconds: int
    total_seconds: int
    channel: str
    service_type: str
    is_escalated: int
    is_abandoned: int
    is_repeat_contact: int
    prior_contacts_30d: int
    has_text: int
    text_length: int
    hour_of_day: int
    is_weekend: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def feature_names() -> list[str]:
    """Column order used by :func:`extract_features` and the CSV export."""
    return [f.name for f in FeatureRow.__dataclass_fields__.values()]


def extract_features(episodes: Iterable[Episode]) -> list[FeatureRow]:
    """Build one feature row per episode.

    Repeat-contact features need the customer's history, so episodes are sorted
    by opening time first and each customer's prior episodes are counted within
    :data:`REPEAT_CONTACT_WINDOW`. Sorting here rather than requiring sorted
    input removes a silent correctness trap: unsorted input would otherwise
    produce plausible but wrong counts.
    """
    ordered = sorted(episodes, key=lambda e: (e.opened_at, e.episode_id))
    history: dict[str, list[Episode]] = defaultdict(list)
    rows: list[FeatureRow] = []

    for episode in ordered:
        previous = history[episode.customer_ref]
        cutoff = episode.opened_at - REPEAT_CONTACT_WINDOW
        prior = sum(1 for earlier in previous if earlier.opened_at >= cutoff)
        text = episode.text or ""

        rows.append(
            FeatureRow(
                episode_id=episode.episode_id,
                tenant_id=episode.tenant_id,
                customer_ref=episode.customer_ref,
                handling_seconds=episode.handling_seconds,
                wait_seconds=episode.wait_seconds,
                total_seconds=episode.handling_seconds + episode.wait_seconds,
                channel=episode.channel.value,
                service_type=episode.service_type,
                is_escalated=int(episode.outcome is Outcome.ESCALATED),
                is_abandoned=int(episode.outcome is Outcome.ABANDONED),
                is_repeat_contact=int(prior > 0),
                prior_contacts_30d=prior,
                has_text=int(bool(text.strip())),
                text_length=len(text),
                hour_of_day=episode.opened_at.hour,
                is_weekend=int(episode.opened_at.weekday() >= 5),
            )
        )
        previous.append(episode)

    return rows


def summarise(rows: Sequence[FeatureRow]) -> dict[str, float]:
    """Descriptive statistics over a feature table.

    Returns an empty mapping for empty input rather than raising: an empty
    nightly batch is a normal state, not an error.
    """
    if not rows:
        return {}
    count = len(rows)
    return {
        "episodes": float(count),
        "customers": float(len({r.customer_ref for r in rows})),
        "mean_handling_seconds": sum(r.handling_seconds for r in rows) / count,
        "mean_wait_seconds": sum(r.wait_seconds for r in rows) / count,
        "escalation_rate": sum(r.is_escalated for r in rows) / count,
        "abandonment_rate": sum(r.is_abandoned for r in rows) / count,
        "repeat_contact_rate": sum(r.is_repeat_contact for r in rows) / count,
        "text_coverage": sum(r.has_text for r in rows) / count,
    }
