"""Edge cases that the happy-path tests do not reach.

Kept in one module so the intent is obvious: these exist to make the error
paths as well tested as the success paths, not to pad the coverage number.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from sqmine.adapters import ContactCentreJsonAdapter, CrmCsvAdapter
from sqmine.agreement import AgreementReport
from sqmine.privacy import Pseudonymiser
from sqmine.schema import Episode, SchemaError

CALL = {
    "call_uuid": "C-1",
    "party": {"customer_id": "CL-500"},
    "started_at": "2026-03-02T09:30:00Z",
    "duration_sec": 420,
    "queue_sec": 60,
    "topic": "transfer",
    "disposition": "resolved",
    "agent_login": "a.smith",
    "transcript": "nothing sensitive here",
}


@pytest.fixture
def pseudonymiser() -> Pseudonymiser:
    return Pseudonymiser(b"edge-case-key")


class TestAdapterConstruction:
    def test_empty_tenant_is_rejected(self, pseudonymiser: Pseudonymiser) -> None:
        with pytest.raises(ValueError, match="tenant_id must not be empty"):
            CrmCsvAdapter("", pseudonymiser)

    def test_direct_iteration_is_refused_with_guidance(
        self, pseudonymiser: Pseudonymiser
    ) -> None:
        adapter = CrmCsvAdapter("t-1", pseudonymiser)
        with pytest.raises(TypeError, match=r"load\(source\)\.episodes"):
            iter(adapter)


class TestContactCentreInputForms:
    def test_file_object_is_accepted(self, pseudonymiser: Pseudonymiser) -> None:
        handle = io.StringIO(json.dumps([CALL]))
        assert ContactCentreJsonAdapter("t-1", pseudonymiser).load(handle).accepted == 1

    def test_bare_list_is_accepted(self, pseudonymiser: Pseudonymiser) -> None:
        assert ContactCentreJsonAdapter("t-1", pseudonymiser).load([CALL]).accepted == 1

    def test_wrapper_without_calls_key_yields_nothing(
        self, pseudonymiser: Pseudonymiser, tmp_path: Path
    ) -> None:
        path = tmp_path / "empty.json"
        path.write_text(json.dumps({"meta": "no calls here"}), encoding="utf-8")
        assert ContactCentreJsonAdapter("t-1", pseudonymiser).load(path).total == 0

    def test_non_list_payload_is_rejected(
        self, pseudonymiser: Pseudonymiser, tmp_path: Path
    ) -> None:
        path = tmp_path / "scalar.json"
        path.write_text("42", encoding="utf-8")
        with pytest.raises(SchemaError, match="expected a list"):
            ContactCentreJsonAdapter("t-1", pseudonymiser).load(path)

    def test_non_object_item_is_rejected(self, pseudonymiser: Pseudonymiser) -> None:
        with pytest.raises(SchemaError, match="expected an object, got str"):
            ContactCentreJsonAdapter("t-1", pseudonymiser).load(["not-an-object"])


class TestContactCentreRejections:
    @pytest.mark.parametrize(
        ("mutation", "expected"),
        [
            ({"party": {}}, "party.customer_id is missing"),
            ({"party": "CL-1"}, "party object is missing"),
            ({"duration_sec": "soon"}, "unparseable duration"),
            ({"duration_sec": -30}, "must not be negative"),
            ({"disposition": "levitated"}, "unknown outcome"),
            ({"started_at": "yesterday"}, "unparseable timestamp"),
        ],
    )
    def test_bad_record_is_rejected_with_a_reason(
        self,
        pseudonymiser: Pseudonymiser,
        mutation: dict[str, object],
        expected: str,
    ) -> None:
        record = {**CALL, **mutation}
        result = ContactCentreJsonAdapter("t-1", pseudonymiser).load([record])
        assert result.rejected == 1
        assert expected in result.rejects[0].reason

    def test_absent_agent_becomes_none(self, pseudonymiser: Pseudonymiser) -> None:
        record = {**CALL, "agent_login": ""}
        episodes = ContactCentreJsonAdapter("t-1", pseudonymiser).load([record]).episodes
        assert episodes[0].operator_ref is None


class TestLoadResultArithmetic:
    def test_empty_load_has_zero_acceptance_rate(
        self, pseudonymiser: Pseudonymiser
    ) -> None:
        result = ContactCentreJsonAdapter("t-1", pseudonymiser).load([])
        assert result.total == 0
        assert result.acceptance_rate == 0.0

    def test_counts_add_up(self, pseudonymiser: Pseudonymiser) -> None:
        records = [CALL, {**CALL, "duration_sec": "soon"}]
        result = ContactCentreJsonAdapter("t-1", pseudonymiser).load(records)
        assert result.total == result.accepted + result.rejected == 2
        assert result.acceptance_rate == 0.5


class TestSchemaErrorPassthrough:
    def test_nested_schema_error_is_not_rewrapped(self) -> None:
        payload = {
            "episode_id": "e-1",
            "tenant_id": "t-1",
            "customer_ref": "c_1",
            "channel": "phone",
            "opened_at": "2026-03-02T09:00:00Z",
            "closed_at": "2026-03-02T08:00:00Z",
            "wait_seconds": 0,
            "service_type": "support",
            "outcome": "resolved",
        }
        with pytest.raises(SchemaError, match="precedes"):
            Episode.from_dict(payload)

    def test_non_integer_wait_is_reported(self) -> None:
        payload = {
            "episode_id": "e-1",
            "tenant_id": "t-1",
            "customer_ref": "c_1",
            "channel": "phone",
            "opened_at": "2026-03-02T09:00:00Z",
            "closed_at": "2026-03-02T09:05:00Z",
            "wait_seconds": "quite a while",
            "service_type": "support",
            "outcome": "resolved",
        }
        with pytest.raises(SchemaError):
            Episode.from_dict(payload)


class TestInterpretationBands:
    """Landis and Koch band boundaries, tested as a pure mapping from kappa.

    Constructing label pairs that land on an exact boundary is fiddly and the
    arithmetic would end up being the thing under test rather than the mapping,
    so the report is built directly.
    """

    @pytest.mark.parametrize(
        ("kappa", "expected"),
        [
            (-0.50, "poor"),
            (-0.01, "poor"),
            (0.00, "slight"),
            (0.20, "slight"),
            (0.21, "fair"),
            (0.40, "fair"),
            (0.41, "moderate"),
            (0.60, "moderate"),
            (0.61, "substantial"),
            (0.80, "substantial"),
            (0.81, "almost perfect"),
            (1.00, "almost perfect"),
        ],
    )
    def test_band_boundaries(self, kappa: float, expected: str) -> None:
        report = AgreementReport(
            items=10,
            labels=("a", "b"),
            observed_agreement=0.5,
            kappa=kappa,
            threshold=0.70,
        )
        assert report.interpretation == expected

    def test_threshold_decides_the_verdict_not_the_band(self) -> None:
        report = AgreementReport(
            items=10,
            labels=("a", "b"),
            observed_agreement=0.9,
            kappa=0.65,
            threshold=0.70,
        )
        assert report.interpretation == "substantial"
        assert not report.passed
