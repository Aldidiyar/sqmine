from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqmine.features import extract_features, feature_names, summarise
from sqmine.schema import Channel, Episode, Outcome

UTC = timezone.utc
BASE = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)


def episode(
    eid: str,
    customer: str = "c_1",
    *,
    offset_days: float = 0.0,
    minutes: int = 5,
    wait: int = 30,
    outcome: Outcome = Outcome.RESOLVED,
    text: str | None = None,
) -> Episode:
    opened = BASE + timedelta(days=offset_days)
    return Episode(
        episode_id=eid,
        tenant_id="t-1",
        customer_ref=customer,
        channel=Channel.PHONE,
        opened_at=opened,
        closed_at=opened + timedelta(minutes=minutes),
        wait_seconds=wait,
        service_type="support",
        outcome=outcome,
        text=text,
    )


class TestExtractFeatures:
    def test_one_row_per_episode(self) -> None:
        rows = extract_features([episode("e-1"), episode("e-2", offset_days=1)])
        assert len(rows) == 2

    def test_durations_are_carried_through(self) -> None:
        row = extract_features([episode("e-1", minutes=7, wait=45)])[0]
        assert row.handling_seconds == 420
        assert row.wait_seconds == 45
        assert row.total_seconds == 465

    def test_outcome_flags(self) -> None:
        rows = extract_features(
            [
                episode("e-1", outcome=Outcome.ESCALATED),
                episode("e-2", offset_days=1, outcome=Outcome.ABANDONED),
                episode("e-3", offset_days=2, outcome=Outcome.RESOLVED),
            ]
        )
        assert [r.is_escalated for r in rows] == [1, 0, 0]
        assert [r.is_abandoned for r in rows] == [0, 1, 0]

    def test_text_features(self) -> None:
        rows = extract_features(
            [episode("e-1", text="hello"), episode("e-2", offset_days=1, text=None)]
        )
        assert (rows[0].has_text, rows[0].text_length) == (1, 5)
        assert (rows[1].has_text, rows[1].text_length) == (0, 0)

    def test_blank_text_does_not_count_as_text(self) -> None:
        assert extract_features([episode("e-1", text="   ")])[0].has_text == 0

    def test_calendar_features(self) -> None:
        row = extract_features([episode("e-1")])[0]
        assert row.hour_of_day == 9
        assert row.is_weekend == 0

    def test_weekend_is_detected(self) -> None:
        # 2026-03-02 is a Monday, so four days later is a Friday and five a Saturday.
        rows = extract_features(
            [episode("e-1", offset_days=4), episode("e-2", offset_days=5)]
        )
        assert [r.is_weekend for r in rows] == [0, 1]


class TestRepeatContact:
    def test_first_contact_is_not_a_repeat(self) -> None:
        assert extract_features([episode("e-1")])[0].is_repeat_contact == 0

    def test_second_contact_within_the_window_is_a_repeat(self) -> None:
        rows = extract_features([episode("e-1"), episode("e-2", offset_days=3)])
        assert [r.is_repeat_contact for r in rows] == [0, 1]
        assert [r.prior_contacts_30d for r in rows] == [0, 1]

    def test_contact_outside_the_window_is_not_a_repeat(self) -> None:
        rows = extract_features([episode("e-1"), episode("e-2", offset_days=31)])
        assert [r.is_repeat_contact for r in rows] == [0, 0]

    def test_contact_exactly_on_the_boundary_counts(self) -> None:
        rows = extract_features([episode("e-1"), episode("e-2", offset_days=30)])
        assert rows[1].prior_contacts_30d == 1

    def test_different_customers_do_not_interfere(self) -> None:
        rows = extract_features(
            [episode("e-1", "c_1"), episode("e-2", "c_2", offset_days=1)]
        )
        assert [r.is_repeat_contact for r in rows] == [0, 0]

    def test_prior_contacts_accumulate(self) -> None:
        rows = extract_features(
            [
                episode("e-1", offset_days=0),
                episode("e-2", offset_days=1),
                episode("e-3", offset_days=2),
            ]
        )
        assert [r.prior_contacts_30d for r in rows] == [0, 1, 2]

    def test_unsorted_input_yields_the_same_result(self) -> None:
        episodes = [episode("e-1"), episode("e-2", offset_days=1)]
        forward = extract_features(episodes)
        backward = extract_features(list(reversed(episodes)))
        assert [r.to_dict() for r in forward] == [r.to_dict() for r in backward]


class TestSummarise:
    def test_empty_input_gives_an_empty_mapping(self) -> None:
        assert summarise([]) == {}

    def test_rates_are_computed(self) -> None:
        rows = extract_features(
            [
                episode("e-1", outcome=Outcome.ESCALATED),
                episode("e-2", "c_2", offset_days=1),
            ]
        )
        stats = summarise(rows)
        assert stats["episodes"] == 2.0
        assert stats["customers"] == 2.0
        assert stats["escalation_rate"] == 0.5

    def test_mean_handling_time(self) -> None:
        rows = extract_features(
            [episode("e-1", minutes=4), episode("e-2", "c_2", minutes=6)]
        )
        assert summarise(rows)["mean_handling_seconds"] == 300.0


def test_feature_names_match_the_dataclass() -> None:
    names = feature_names()
    row = extract_features([episode("e-1")])[0]
    assert names == list(row.to_dict().keys())
    assert "episode_id" in names and "prior_contacts_30d" in names
