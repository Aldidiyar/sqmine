from __future__ import annotations

from pathlib import Path

import pytest

from sqmine.privacy import Pseudonymiser, redact_text


@pytest.fixture
def pseudonymiser() -> Pseudonymiser:
    return Pseudonymiser(b"test-key-not-for-production")


class TestPseudonymiser:
    def test_same_input_gives_same_reference(self, pseudonymiser: Pseudonymiser) -> None:
        assert pseudonymiser.ref("900101300123") == pseudonymiser.ref("900101300123")

    def test_different_inputs_give_different_references(
        self, pseudonymiser: Pseudonymiser
    ) -> None:
        assert pseudonymiser.ref("alice") != pseudonymiser.ref("bob")

    def test_different_keys_give_different_references(self) -> None:
        a = Pseudonymiser(b"key-one").ref("alice")
        b = Pseudonymiser(b"key-two").ref("alice")
        assert a != b

    def test_reference_does_not_contain_the_input(
        self, pseudonymiser: Pseudonymiser
    ) -> None:
        assert "900101300123" not in pseudonymiser.ref("900101300123")

    def test_whitespace_and_case_are_normalised(
        self, pseudonymiser: Pseudonymiser
    ) -> None:
        assert pseudonymiser.ref("  AB-1 ") == pseudonymiser.ref("ab-1")

    def test_prefix_is_applied(self, pseudonymiser: Pseudonymiser) -> None:
        assert pseudonymiser.ref("alice", prefix="c_").startswith("c_")

    def test_digest_length_is_configurable(self) -> None:
        short = Pseudonymiser(b"k", digest_chars=8).ref("alice")
        assert len(short) == 8

    def test_empty_value_is_rejected(self, pseudonymiser: Pseudonymiser) -> None:
        with pytest.raises(ValueError, match="empty value"):
            pseudonymiser.ref("   ")

    def test_empty_key_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="key must not be empty"):
            Pseudonymiser(b"")

    @pytest.mark.parametrize("chars", [4, 100])
    def test_out_of_range_digest_length_is_rejected(self, chars: int) -> None:
        with pytest.raises(ValueError, match="digest_chars"):
            Pseudonymiser(b"k", digest_chars=chars)

    def test_ref_or_none_passes_absent_values_through(
        self, pseudonymiser: Pseudonymiser
    ) -> None:
        assert pseudonymiser.ref_or_none(None) is None
        assert pseudonymiser.ref_or_none("") is None
        assert pseudonymiser.ref_or_none("  ") is None

    def test_ref_or_none_pseudonymises_present_values(
        self, pseudonymiser: Pseudonymiser
    ) -> None:
        assert pseudonymiser.ref_or_none("alice") == pseudonymiser.ref("alice")

    def test_key_is_loaded_from_file(self, tmp_path: Path) -> None:
        key_file = tmp_path / "key.txt"
        key_file.write_bytes(b"file-key\n")
        from_file = Pseudonymiser.from_file(key_file)
        assert from_file.ref("alice") == Pseudonymiser(b"file-key").ref("alice")

    def test_empty_key_file_is_rejected(self, tmp_path: Path) -> None:
        key_file = tmp_path / "empty.txt"
        key_file.write_bytes(b"   \n")
        with pytest.raises(ValueError, match="is empty"):
            Pseudonymiser.from_file(key_file)


class TestRedactText:
    def test_none_passes_through(self) -> None:
        assert redact_text(None) is None

    def test_plain_text_is_untouched(self) -> None:
        assert redact_text("the queue was long") == "the queue was long"

    def test_email_is_redacted(self) -> None:
        assert redact_text("write to a.b@example.kz please") == (
            "write to [EMAIL] please"
        )

    def test_phone_is_redacted(self) -> None:
        assert "[PHONE]" in redact_text("call +7 701 234 56 78 tomorrow")  # type: ignore[operator]

    def test_short_numbers_are_preserved(self) -> None:
        assert redact_text("waited 15 minutes") == "waited 15 minutes"
