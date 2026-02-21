from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from sqmine.adapters import (
    ContactCentreJsonAdapter,
    CrmCsvAdapter,
    available_adapters,
    get_adapter,
    register_adapter,
)
from sqmine.adapters.base import SourceAdapter
from sqmine.privacy import Pseudonymiser
from sqmine.schema import Channel, Episode, Outcome

CRM_CSV = """TRX_ID,CLIENT_NO,DT_OPEN,DURATION_MIN,WAIT_SEC,CHANNEL,SERVICE,STATUS,OPERATOR,COMMENT
T-1,CL-100,2026-03-02T09:00:00,7.5,45,office,card-dispute,closed,OP-9,all fine
T-2,CL-101,2026-03-02T10:15:00,3,120,call,balance,complaint,OP-7,call me on 701 234 56 78
T-3,CL-100,2026-03-05T11:00:00,12,0,chat,card-dispute,ok,,
"""

CALLS = {
    "calls": [
        {
            "call_uuid": "C-1",
            "party": {"customer_id": "CL-500"},
            "started_at": "2026-03-02T09:30:00Z",
            "duration_sec": 420,
            "queue_sec": 60,
            "topic": "transfer",
            "disposition": "resolved",
            "agent_login": "a.smith",
            "transcript": "my id is 900101300123",
        }
    ]
}


@pytest.fixture
def pseudonymiser() -> Pseudonymiser:
    return Pseudonymiser(b"test-key")


class TestRegistry:
    def test_built_in_adapters_are_registered(self) -> None:
        assert "crm-csv" in available_adapters()
        assert "contact-centre-json" in available_adapters()

    def test_lookup_returns_the_class(self) -> None:
        assert get_adapter("crm-csv") is CrmCsvAdapter

    def test_unknown_adapter_lists_the_known_ones(self) -> None:
        with pytest.raises(KeyError, match="known adapters"):
            get_adapter("carrier-pigeon")

    def test_nameless_adapter_is_rejected(self) -> None:
        class Nameless(SourceAdapter):
            def read_rows(self, source: object) -> list[dict[str, object]]:
                return []

            def build_episode(self, row: dict[str, object]) -> Episode:
                raise NotImplementedError

        with pytest.raises(ValueError, match="non-empty name"):
            register_adapter(Nameless)

    def test_duplicate_registration_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="already registered"):
            register_adapter(CrmCsvAdapter)


class TestCrmCsvAdapter:
    def test_all_valid_rows_are_accepted(self, pseudonymiser: Pseudonymiser) -> None:
        result = CrmCsvAdapter("t-1", pseudonymiser).load(io.StringIO(CRM_CSV))
        assert result.accepted == 3
        assert result.rejected == 0
        assert result.acceptance_rate == 1.0

    def test_duration_becomes_a_closing_timestamp(
        self, pseudonymiser: Pseudonymiser
    ) -> None:
        episodes = CrmCsvAdapter("t-1", pseudonymiser).load(io.StringIO(CRM_CSV)).episodes
        assert episodes[0].handling_seconds == 450

    def test_channel_and_outcome_are_normalised(
        self, pseudonymiser: Pseudonymiser
    ) -> None:
        episodes = CrmCsvAdapter("t-1", pseudonymiser).load(io.StringIO(CRM_CSV)).episodes
        assert episodes[0].channel is Channel.BRANCH
        assert episodes[1].outcome is Outcome.ESCALATED

    def test_customer_identifier_never_reaches_the_episode(
        self, pseudonymiser: Pseudonymiser
    ) -> None:
        episodes = CrmCsvAdapter("t-1", pseudonymiser).load(io.StringIO(CRM_CSV)).episodes
        serialised = " ".join(e.to_json() for e in episodes)
        assert "CL-100" not in serialised
        assert "OP-9" not in serialised

    def test_same_customer_keeps_one_reference(
        self, pseudonymiser: Pseudonymiser
    ) -> None:
        episodes = CrmCsvAdapter("t-1", pseudonymiser).load(io.StringIO(CRM_CSV)).episodes
        assert episodes[0].customer_ref == episodes[2].customer_ref
        assert episodes[0].customer_ref != episodes[1].customer_ref

    def test_free_text_is_redacted(self, pseudonymiser: Pseudonymiser) -> None:
        episodes = CrmCsvAdapter("t-1", pseudonymiser).load(io.StringIO(CRM_CSV)).episodes
        assert episodes[1].text is not None
        assert "701 234 56 78" not in episodes[1].text

    def test_absent_operator_becomes_none(self, pseudonymiser: Pseudonymiser) -> None:
        episodes = CrmCsvAdapter("t-1", pseudonymiser).load(io.StringIO(CRM_CSV)).episodes
        assert episodes[2].operator_ref is None

    def test_tenant_is_stamped_on_every_episode(
        self, pseudonymiser: Pseudonymiser
    ) -> None:
        episodes = (
            CrmCsvAdapter("branch-bank", pseudonymiser)
            .load(io.StringIO(CRM_CSV))
            .episodes
        )
        assert {e.tenant_id for e in episodes} == {"branch-bank"}

    def test_file_input_is_supported(
        self, pseudonymiser: Pseudonymiser, tmp_path: Path
    ) -> None:
        path = tmp_path / "crm.csv"
        path.write_text(CRM_CSV, encoding="utf-8")
        assert CrmCsvAdapter("t-1", pseudonymiser).load(path).accepted == 3

    def test_custom_mapping_overrides_the_default(
        self, pseudonymiser: Pseudonymiser
    ) -> None:
        csv_text = CRM_CSV.replace("TRX_ID", "ID_TRANSACTION")
        adapter = CrmCsvAdapter(
            "t-1", pseudonymiser, mapping={"episode_id": "ID_TRANSACTION"}
        )
        assert adapter.load(io.StringIO(csv_text)).accepted == 3


class TestCrmCsvRejections:
    @pytest.mark.parametrize(
        ("bad_row", "expected"),
        [
            ("T-9,,2026-03-02T09:00:00,5,0,call,x,ok,,", "customer identifier"),
            ("T-9,CL-1,not-a-date,5,0,call,x,ok,,", "unparseable timestamp"),
            ("T-9,CL-1,2026-03-02T09:00:00,abc,0,call,x,ok,,", "unparseable duration"),
            ("T-9,CL-1,2026-03-02T09:00:00,-5,0,call,x,ok,,", "must not be negative"),
            ("T-9,CL-1,2026-03-02T09:00:00,5,0,pigeon,x,ok,,", "unknown channel"),
            ("T-9,CL-1,2026-03-02T09:00:00,5,0,call,x,maybe,,", "unknown outcome"),
            (",CL-1,2026-03-02T09:00:00,5,0,call,x,ok,,", "episode_id must not be empty"),
        ],
    )
    def test_bad_row_is_rejected_with_a_reason(
        self, pseudonymiser: Pseudonymiser, bad_row: str, expected: str
    ) -> None:
        header = CRM_CSV.splitlines()[0]
        result = CrmCsvAdapter("t-1", pseudonymiser).load(
            io.StringIO(f"{header}\n{bad_row}\n")
        )
        assert result.accepted == 0
        assert result.rejected == 1
        assert expected in result.rejects[0].reason

    def test_good_rows_survive_a_bad_neighbour(
        self, pseudonymiser: Pseudonymiser
    ) -> None:
        broken = CRM_CSV + "T-4,CL-1,not-a-date,5,0,call,x,ok,,\n"
        result = CrmCsvAdapter("t-1", pseudonymiser).load(io.StringIO(broken))
        assert result.accepted == 3
        assert result.rejected == 1
        assert result.rejects[0].index == 3

    def test_summary_reports_both_counts(self, pseudonymiser: Pseudonymiser) -> None:
        broken = CRM_CSV + "T-4,CL-1,not-a-date,5,0,call,x,ok,,\n"
        summary = CrmCsvAdapter("t-1", pseudonymiser).load(io.StringIO(broken)).summary()
        assert "3/4" in summary and "1 rejected" in summary


class TestContactCentreJsonAdapter:
    def test_nested_customer_is_read(self, pseudonymiser: Pseudonymiser) -> None:
        result = ContactCentreJsonAdapter("t-1", pseudonymiser).load(CALLS["calls"])
        assert result.accepted == 1
        assert result.episodes[0].customer_ref.startswith("c_")

    def test_channel_is_always_phone(self, pseudonymiser: Pseudonymiser) -> None:
        episodes = (
            ContactCentreJsonAdapter("t-1", pseudonymiser).load(CALLS["calls"]).episodes
        )
        assert episodes[0].channel is Channel.PHONE

    def test_transcript_is_redacted(self, pseudonymiser: Pseudonymiser) -> None:
        episodes = (
            ContactCentreJsonAdapter("t-1", pseudonymiser).load(CALLS["calls"]).episodes
        )
        assert episodes[0].text == "my id is [ID]"

    def test_wrapper_object_is_unwrapped(
        self, pseudonymiser: Pseudonymiser, tmp_path: Path
    ) -> None:
        path = tmp_path / "calls.json"
        path.write_text(json.dumps(CALLS), encoding="utf-8")
        assert ContactCentreJsonAdapter("t-1", pseudonymiser).load(path).accepted == 1

    def test_missing_party_is_rejected(self, pseudonymiser: Pseudonymiser) -> None:
        row = {k: v for k, v in CALLS["calls"][0].items() if k != "party"}
        result = ContactCentreJsonAdapter("t-1", pseudonymiser).load([row])
        assert result.rejected == 1
        assert "party object is missing" in result.rejects[0].reason

    def test_both_adapters_agree_on_the_same_customer(
        self, pseudonymiser: Pseudonymiser
    ) -> None:
        """The whole point of a canonical schema: one person, one reference."""
        csv_text = (
            "TRX_ID,CLIENT_NO,DT_OPEN,DURATION_MIN,WAIT_SEC,"
            "CHANNEL,SERVICE,STATUS,OPERATOR,COMMENT\n"
            "T-1,CL-500,2026-03-02T09:00:00,5,0,office,x,ok,,\n"
        )
        from_csv = CrmCsvAdapter("t-1", pseudonymiser).load(io.StringIO(csv_text))
        from_json = ContactCentreJsonAdapter("t-1", pseudonymiser).load(CALLS["calls"])
        assert from_csv.episodes[0].customer_ref == from_json.episodes[0].customer_ref
