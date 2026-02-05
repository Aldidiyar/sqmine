from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from sqmine.schema import (
    SCHEMA_VERSION,
    Channel,
    Episode,
    Outcome,
    SchemaError,
    parse_timestamp,
)

UTC = timezone.utc


def make_episode(**overrides: object) -> Episode:
    base: dict[str, object] = {
        "episode_id": "e-1",
        "tenant_id": "t-1",
        "customer_ref": "c_abc",
        "channel": Channel.PHONE,
        "opened_at": datetime(2026, 3, 2, 9, 0, tzinfo=UTC),
        "closed_at": datetime(2026, 3, 2, 9, 7, tzinfo=UTC),
        "wait_seconds": 45,
        "service_type": "card-dispute",
        "outcome": Outcome.RESOLVED,
    }
    base.update(overrides)
    return Episode(**base)  # type: ignore[arg-type]


class TestEpisodeValidation:
    def test_valid_episode_is_constructed(self) -> None:
        episode = make_episode()
        assert episode.episode_id == "e-1"
        assert episode.schema_version == SCHEMA_VERSION

    def test_handling_seconds_is_derived(self) -> None:
        assert make_episode().handling_seconds == 420

    @pytest.mark.parametrize(
        "field", ["episode_id", "tenant_id", "customer_ref", "service_type"]
    )
    def test_empty_required_field_is_rejected(self, field: str) -> None:
        with pytest.raises(SchemaError, match=f"{field} must not be empty"):
            make_episode(**{field: ""})

    def test_closing_before_opening_is_rejected(self) -> None:
        with pytest.raises(SchemaError, match="precedes"):
            make_episode(closed_at=datetime(2026, 3, 2, 8, 0, tzinfo=UTC))

    def test_equal_timestamps_are_allowed(self) -> None:
        moment = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)
        assert make_episode(opened_at=moment, closed_at=moment).handling_seconds == 0

    def test_negative_wait_is_rejected(self) -> None:
        with pytest.raises(SchemaError, match="wait_seconds"):
            make_episode(wait_seconds=-1)

    def test_naive_timestamp_is_rejected(self) -> None:
        with pytest.raises(SchemaError, match="timezone-aware"):
            make_episode(opened_at=datetime(2026, 3, 2, 9, 0))

    def test_episode_is_immutable(self) -> None:
        with pytest.raises((AttributeError, TypeError)):
            make_episode().episode_id = "changed"  # type: ignore[misc]


class TestSerialisation:
    def test_round_trip_preserves_every_field(self) -> None:
        original = make_episode(operator_ref="o_1", text="hello")
        restored = Episode.from_dict(original.to_dict())
        assert restored == original

    def test_to_json_is_single_line(self) -> None:
        assert "\n" not in make_episode().to_json()

    def test_missing_field_is_reported_by_name(self) -> None:
        payload = make_episode().to_dict()
        del payload["wait_seconds"]
        with pytest.raises(SchemaError, match="missing field: wait_seconds"):
            Episode.from_dict(payload)

    def test_invalid_enum_is_rejected(self) -> None:
        payload = make_episode().to_dict()
        payload["outcome"] = "teleported"
        with pytest.raises(SchemaError):
            Episode.from_dict(payload)


class TestEnumParsing:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("branch", Channel.BRANCH),
            ("Office", Channel.BRANCH),
            ("  CALL ", Channel.PHONE),
            ("chat", Channel.WEB),
            ("Mail", Channel.EMAIL),
        ],
    )
    def test_channel_aliases(self, raw: str, expected: Channel) -> None:
        assert Channel.parse(raw) is expected

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("ok", Outcome.RESOLVED),
            ("CLOSED", Outcome.RESOLVED),
            ("complaint", Outcome.ESCALATED),
            ("dropped", Outcome.ABANDONED),
        ],
    )
    def test_outcome_aliases(self, raw: str, expected: Outcome) -> None:
        assert Outcome.parse(raw) is expected

    def test_unknown_channel_names_the_value(self) -> None:
        with pytest.raises(SchemaError, match="unknown channel: 'pigeon'"):
            Channel.parse("pigeon")

    def test_unknown_outcome_names_the_value(self) -> None:
        with pytest.raises(SchemaError, match="unknown outcome"):
            Outcome.parse("maybe")


class TestParseTimestamp:
    def test_naive_input_is_assumed_utc(self) -> None:
        assert parse_timestamp("2026-03-02T09:00:00").tzinfo is UTC

    def test_offset_is_preserved(self) -> None:
        parsed = parse_timestamp("2026-03-02T09:00:00+05:00")
        assert parsed.utcoffset() == timedelta(hours=5)

    def test_zulu_suffix_is_accepted(self) -> None:
        assert parse_timestamp("2026-03-02T09:00:00Z").tzinfo is not None

    def test_datetime_passes_through(self) -> None:
        moment = datetime(2026, 3, 2, 9, 0, tzinfo=UTC)
        assert parse_timestamp(moment) == moment

    def test_garbage_is_rejected(self) -> None:
        with pytest.raises(SchemaError, match="unparseable timestamp"):
            parse_timestamp("last tuesday")
