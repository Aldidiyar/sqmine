"""Adapter for CRM transaction-log exports delivered as CSV.

The source names its columns in upper snake case, records local timestamps
without an offset and has no closing timestamp at all: it stores a duration in
minutes instead. Every one of those quirks is absorbed here.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any, ClassVar, TextIO

from sqmine.adapters.base import SourceAdapter, register_adapter
from sqmine.privacy import redact_text
from sqmine.schema import Channel, Episode, Outcome, SchemaError, parse_timestamp


@register_adapter
class CrmCsvAdapter(SourceAdapter):
    """Reads the nightly CRM export."""

    name: ClassVar[str] = "crm-csv"
    default_mapping: ClassVar[dict[str, str]] = {
        "episode_id": "TRX_ID",
        "customer_id": "CLIENT_NO",
        "opened_at": "DT_OPEN",
        "duration_min": "DURATION_MIN",
        "wait_seconds": "WAIT_SEC",
        "channel": "CHANNEL",
        "service_type": "SERVICE",
        "outcome": "STATUS",
        "operator_id": "OPERATOR",
        "text": "COMMENT",
    }

    def read_rows(self, source: str | Path | TextIO) -> Iterable[dict[str, Any]]:
        if isinstance(source, (str, Path)):
            with Path(source).open(newline="", encoding="utf-8-sig") as handle:
                yield from csv.DictReader(handle)
        else:
            yield from csv.DictReader(source)

    def build_episode(self, row: dict[str, Any]) -> Episode:
        opened_at = parse_timestamp(self.field(row, "opened_at"))
        duration = self.field(row, "duration_min")
        try:
            minutes = float(duration)
        except (TypeError, ValueError) as exc:
            raise SchemaError(f"unparseable duration: {duration!r}") from exc
        if minutes < 0:
            raise SchemaError("duration must not be negative")

        customer_id = self.field(row, "customer_id")
        if not customer_id or not str(customer_id).strip():
            raise SchemaError("customer identifier is missing")

        return Episode(
            episode_id=str(self.field(row, "episode_id") or "").strip(),
            tenant_id=self.tenant_id,
            customer_ref=self.pseudonymiser.ref(str(customer_id), prefix="c_"),
            channel=Channel.parse(str(self.field(row, "channel") or "")),
            opened_at=opened_at,
            closed_at=opened_at + timedelta(minutes=minutes),
            wait_seconds=int(float(self.field(row, "wait_seconds") or 0)),
            service_type=str(self.field(row, "service_type") or "").strip(),
            outcome=Outcome.parse(str(self.field(row, "outcome") or "")),
            operator_ref=self.pseudonymiser.ref_or_none(
                self.field(row, "operator_id"), prefix="o_"
            ),
            text=redact_text(self.field(row, "text")),
        )


def iter_episodes(
    adapter: CrmCsvAdapter, source: str | Path | TextIO
) -> Iterator[Episode]:  # pragma: no cover - thin helper
    """Convenience wrapper yielding only the accepted episodes."""
    yield from adapter.load(source).episodes
