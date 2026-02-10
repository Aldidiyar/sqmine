"""The source port: everything external enters through an adapter.

``SourceAdapter`` is the port. Each concrete adapter is a plug for one source
system: it knows that system's field names, date formats and quirks, and
nothing else in the package does. Adding a source, or onboarding a second
organisation, means writing an adapter and a mapping, not editing the core.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any, ClassVar

from sqmine.privacy import Pseudonymiser
from sqmine.schema import Episode, SchemaError

__all__ = ["LoadResult", "Reject", "SourceAdapter", "get_adapter", "register_adapter"]

_REGISTRY: dict[str, type[SourceAdapter]] = {}


@dataclass(frozen=True, slots=True)
class Reject:
    """One row that could not be converted, with the reason why."""

    index: int
    reason: str
    raw: dict[str, Any]


@dataclass(slots=True)
class LoadResult:
    """Outcome of a load: what was accepted, and what was not.

    Rejects are collected rather than raised. A single malformed row in a
    nightly export should not abort the batch, but it must not vanish either,
    so every rejection is reported with its row index and reason.
    """

    episodes: list[Episode] = field(default_factory=list)
    rejects: list[Reject] = field(default_factory=list)

    @property
    def accepted(self) -> int:
        return len(self.episodes)

    @property
    def rejected(self) -> int:
        return len(self.rejects)

    @property
    def total(self) -> int:
        return self.accepted + self.rejected

    @property
    def acceptance_rate(self) -> float:
        """Share of rows converted, in the range 0.0 to 1.0."""
        return self.accepted / self.total if self.total else 0.0

    def summary(self) -> str:
        return (
            f"{self.accepted}/{self.total} rows accepted "
            f"({self.acceptance_rate:.1%}), {self.rejected} rejected"
        )


class SourceAdapter(ABC):
    """Base class for source adapters.

    Subclasses implement :meth:`read_rows` and :meth:`build_episode`.
    :meth:`load` is deliberately not overridable in spirit: it fixes the order
    of operations, so no adapter can accidentally skip pseudonymisation.
    """

    name: ClassVar[str] = ""
    #: Canonical field -> source field. Overridden per tenant via configuration.
    default_mapping: ClassVar[dict[str, str]] = {}

    def __init__(
        self,
        tenant_id: str,
        pseudonymiser: Pseudonymiser,
        mapping: dict[str, str] | None = None,
    ) -> None:
        if not tenant_id:
            raise ValueError("tenant_id must not be empty")
        self.tenant_id = tenant_id
        self.pseudonymiser = pseudonymiser
        self.mapping = {**self.default_mapping, **(mapping or {})}

    @abstractmethod
    def read_rows(self, source: Any) -> Iterable[dict[str, Any]]:
        """Yield raw rows from the source, without interpreting them."""

    @abstractmethod
    def build_episode(self, row: dict[str, Any]) -> Episode:
        """Convert one raw row into a canonical Episode."""

    def field(self, row: dict[str, Any], canonical: str) -> Any:
        """Read a canonical field from a raw row using the active mapping."""
        return row.get(self.mapping.get(canonical, canonical))

    def load(self, source: Any) -> LoadResult:
        """Convert a whole source into episodes, collecting rejections."""
        result = LoadResult()
        for index, row in enumerate(self.read_rows(source)):
            try:
                result.episodes.append(self.build_episode(row))
            except (SchemaError, ValueError, TypeError, KeyError) as exc:
                result.rejects.append(Reject(index=index, reason=str(exc), raw=row))
        return result

    def __iter__(self) -> Iterator[Episode]:  # pragma: no cover - convenience only
        raise TypeError("iterate over load(source).episodes instead")


def register_adapter(cls: type[SourceAdapter]) -> type[SourceAdapter]:
    """Class decorator that adds an adapter to the registry."""
    if not cls.name:
        raise ValueError(f"{cls.__name__} must define a non-empty name")
    if cls.name in _REGISTRY:
        raise ValueError(f"adapter {cls.name!r} is already registered")
    _REGISTRY[cls.name] = cls
    return cls


def get_adapter(name: str) -> type[SourceAdapter]:
    """Look up a registered adapter by name."""
    try:
        return _REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY)) or "none registered"
        raise KeyError(f"unknown adapter {name!r}; known adapters: {known}") from None


def available_adapters() -> list[str]:
    """Names of every registered adapter, sorted."""
    return sorted(_REGISTRY)
