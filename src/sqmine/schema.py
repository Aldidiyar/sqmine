"""The canonical service-episode record.

Every source system is translated into this shape before anything downstream
touches it. The schema is deliberately rigid: it is the contract the rest of
the package is organised around, and changing it invalidates every stored
episode, every feature vector and every trained model.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

SCHEMA_VERSION = "1.0"


class SchemaError(ValueError):
    """Raised when a record cannot be represented as a valid Episode."""


class Channel(str, Enum):
    """How the customer reached the organisation."""

    BRANCH = "branch"
    PHONE = "phone"
    WEB = "web"
    EMAIL = "email"

    @classmethod
    def parse(cls, raw: str) -> Channel:
        key = (raw or "").strip().lower()
        aliases = {
            "office": cls.BRANCH,
            "branch": cls.BRANCH,
            "call": cls.PHONE,
            "phone": cls.PHONE,
            "voice": cls.PHONE,
            "chat": cls.WEB,
            "web": cls.WEB,
            "online": cls.WEB,
            "mail": cls.EMAIL,
            "email": cls.EMAIL,
        }
        if key in aliases:
            return aliases[key]
        raise SchemaError(f"unknown channel: {raw!r}")


class Outcome(str, Enum):
    """How the episode ended."""

    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    ESCALATED = "escalated"
    ABANDONED = "abandoned"

    @classmethod
    def parse(cls, raw: str) -> Outcome:
        key = (raw or "").strip().lower()
        aliases = {
            "ok": cls.RESOLVED,
            "closed": cls.RESOLVED,
            "resolved": cls.RESOLVED,
            "open": cls.UNRESOLVED,
            "unresolved": cls.UNRESOLVED,
            "escalated": cls.ESCALATED,
            "complaint": cls.ESCALATED,
            "abandoned": cls.ABANDONED,
            "dropped": cls.ABANDONED,
        }
        if key in aliases:
            return aliases[key]
        raise SchemaError(f"unknown outcome: {raw!r}")


@dataclass(frozen=True, slots=True)
class Episode:
    """One service episode, normalised and already pseudonymised.

    Identifiers reaching this record must already be pseudonymised. The class
    does not pseudonymise anything itself: that happens in the adapter, at the
    trust boundary, so there is exactly one place to audit.
    """

    episode_id: str
    tenant_id: str
    customer_ref: str
    channel: Channel
    opened_at: datetime
    closed_at: datetime
    wait_seconds: int
    service_type: str
    outcome: Outcome
    operator_ref: str | None = None
    text: str | None = None
    schema_version: str = field(default=SCHEMA_VERSION)

    def __post_init__(self) -> None:
        for name in ("episode_id", "tenant_id", "customer_ref", "service_type"):
            if not getattr(self, name):
                raise SchemaError(f"{name} must not be empty")
        if self.opened_at.tzinfo is None or self.closed_at.tzinfo is None:
            raise SchemaError("opened_at and closed_at must be timezone-aware")
        if self.closed_at < self.opened_at:
            raise SchemaError(
                f"closed_at {self.closed_at.isoformat()} precedes "
                f"opened_at {self.opened_at.isoformat()}"
            )
        if self.wait_seconds < 0:
            raise SchemaError("wait_seconds must not be negative")

    @property
    def handling_seconds(self) -> int:
        """Elapsed time from opening to closing, in whole seconds."""
        return int((self.closed_at - self.opened_at).total_seconds())

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-compatible dictionary."""
        raw = asdict(self)
        raw["channel"] = self.channel.value
        raw["outcome"] = self.outcome.value
        raw["opened_at"] = self.opened_at.isoformat()
        raw["closed_at"] = self.closed_at.isoformat()
        return raw

    def to_json(self) -> str:
        """Serialise to a single-line JSON string, suitable for JSON Lines."""
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Episode:
        """Rebuild an Episode from :meth:`to_dict` output."""
        try:
            return cls(
                episode_id=str(raw["episode_id"]),
                tenant_id=str(raw["tenant_id"]),
                customer_ref=str(raw["customer_ref"]),
                channel=Channel(raw["channel"]),
                opened_at=parse_timestamp(raw["opened_at"]),
                closed_at=parse_timestamp(raw["closed_at"]),
                wait_seconds=int(raw["wait_seconds"]),
                service_type=str(raw["service_type"]),
                outcome=Outcome(raw["outcome"]),
                operator_ref=raw.get("operator_ref"),
                text=raw.get("text"),
                schema_version=str(raw.get("schema_version", SCHEMA_VERSION)),
            )
        except KeyError as exc:
            raise SchemaError(f"missing field: {exc.args[0]}") from exc
        except ValueError as exc:
            if isinstance(exc, SchemaError):
                raise
            raise SchemaError(str(exc)) from exc


def parse_timestamp(raw: str | datetime) -> datetime:
    """Parse an ISO-8601 timestamp, assuming UTC when no offset is given.

    Source systems are inconsistent about offsets. Rather than let each adapter
    invent its own rule, the decision is made once, here: a naive timestamp is
    treated as UTC.
    """
    if isinstance(raw, datetime):
        value = raw
    else:
        text = str(raw).strip().replace("Z", "+00:00")
        try:
            value = datetime.fromisoformat(text)
        except ValueError as exc:
            raise SchemaError(f"unparseable timestamp: {raw!r}") from exc
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
