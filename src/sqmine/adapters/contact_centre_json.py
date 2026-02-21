"""Adapter for contact-centre call records delivered as JSON.

This source is shaped differently from the CRM in three ways that matter: it
nests the customer under a ``party`` object, it reports duration in seconds,
and it carries a transcript whose text contains personal data inline.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import timedelta
from pathlib import Path
from typing import Any, ClassVar, TextIO

from sqmine.adapters.base import SourceAdapter, register_adapter
from sqmine.privacy import redact_text
from sqmine.schema import Channel, Episode, Outcome, SchemaError, parse_timestamp


@register_adapter
class ContactCentreJsonAdapter(SourceAdapter):
    """Reads contact-centre call records."""

    name: ClassVar[str] = "contact-centre-json"
    default_mapping: ClassVar[dict[str, str]] = {
        "episode_id": "call_uuid",
        "opened_at": "started_at",
        "duration_sec": "duration_sec",
        "wait_seconds": "queue_sec",
        "service_type": "topic",
        "outcome": "disposition",
        "operator_id": "agent_login",
        "text": "transcript",
    }

    def read_rows(
        self, source: str | Path | TextIO | list[Any]
    ) -> Iterable[dict[str, Any]]:
        if isinstance(source, list):
            payload: Any = source
        elif isinstance(source, (str, Path)):
            payload = json.loads(Path(source).read_text(encoding="utf-8"))
        else:
            payload = json.load(source)

        if isinstance(payload, dict):
            payload = payload.get("calls", [])
        if not isinstance(payload, list):
            raise SchemaError("expected a list of call records")
        for item in payload:
            if not isinstance(item, dict):
                raise SchemaError(f"expected an object, got {type(item).__name__}")
            yield item

    def build_episode(self, row: dict[str, Any]) -> Episode:
        party = row.get("party")
        if not isinstance(party, dict):
            raise SchemaError("party object is missing")
        customer_id = party.get("customer_id")
        if not customer_id:
            raise SchemaError("party.customer_id is missing")

        opened_at = parse_timestamp(self.field(row, "opened_at"))
        seconds = self.field(row, "duration_sec")
        try:
            duration = int(seconds)
        except (TypeError, ValueError) as exc:
            raise SchemaError(f"unparseable duration: {seconds!r}") from exc
        if duration < 0:
            raise SchemaError("duration must not be negative")

        return Episode(
            episode_id=str(self.field(row, "episode_id") or "").strip(),
            tenant_id=self.tenant_id,
            customer_ref=self.pseudonymiser.ref(str(customer_id), prefix="c_"),
            channel=Channel.PHONE,
            opened_at=opened_at,
            closed_at=opened_at + timedelta(seconds=duration),
            wait_seconds=int(self.field(row, "wait_seconds") or 0),
            service_type=str(self.field(row, "service_type") or "").strip(),
            outcome=Outcome.parse(str(self.field(row, "outcome") or "")),
            operator_ref=self.pseudonymiser.ref_or_none(
                self.field(row, "operator_id"), prefix="o_"
            ),
            text=redact_text(self.field(row, "text")),
        )
