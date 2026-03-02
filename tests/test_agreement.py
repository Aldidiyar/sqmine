from __future__ import annotations

import pytest

from sqmine.agreement import (
    AgreementError,
    cohens_kappa,
    confusion_matrix,
    observed_agreement,
    score_agreement,
)


class TestObservedAgreement:
    def test_identical_labelling(self) -> None:
        assert observed_agreement(["a", "b"], ["a", "b"]) == 1.0

    def test_complete_disagreement(self) -> None:
        assert observed_agreement(["a", "a"], ["b", "b"]) == 0.0

    def test_partial_agreement(self) -> None:
        assert observed_agreement(["a", "b", "a"], ["a", "b", "b"]) == pytest.approx(
            2 / 3
        )


class TestCohensKappa:
    def test_perfect_agreement_is_one(self) -> None:
        a = ["good", "bad", "good", "bad"]
        assert cohens_kappa(a, a) == pytest.approx(1.0)

    def test_chance_level_agreement_is_about_zero(self) -> None:
        a = ["good", "good", "bad", "bad"]
        b = ["good", "bad", "good", "bad"]
        assert cohens_kappa(a, b) == pytest.approx(0.0, abs=1e-9)

    def test_systematic_disagreement_is_negative(self) -> None:
        a = ["good", "good", "bad", "bad"]
        b = ["bad", "bad", "good", "good"]
        assert cohens_kappa(a, b) < 0

    def test_hand_computed_textbook_value(self) -> None:
        """Fifty items: 20 both-yes, 15 both-no, 10 yes/no, 5 no/yes.

        p_o   = 35/50 = 0.70
        A marginals 30/20, B marginals 25/25
        p_e   = (30/50)(25/50) + (20/50)(25/50) = 0.30 + 0.20 = 0.50
        kappa = (0.70 - 0.50) / (1 - 0.50) = 0.40
        """
        a = ["y"] * 20 + ["n"] * 15 + ["y"] * 10 + ["n"] * 5
        b = ["y"] * 20 + ["n"] * 15 + ["n"] * 10 + ["y"] * 5
        assert observed_agreement(a, b) == pytest.approx(0.70)
        assert cohens_kappa(a, b) == pytest.approx(0.40)

    def test_agreement_below_chance_is_negative(self) -> None:
        """Marginals 13/7 for both, only 10 of 20 agreements.

        p_e = (13/20)^2 + (7/20)^2 = 0.545, which exceeds p_o = 0.50, so the
        annotators agree less than chance alone would predict.
        """
        a = ["y"] * 8 + ["n"] * 2 + ["y"] * 5 + ["n"] * 5
        b = ["y"] * 8 + ["n"] * 2 + ["n"] * 5 + ["y"] * 5
        assert observed_agreement(a, b) == pytest.approx(0.50)
        assert cohens_kappa(a, b) == pytest.approx((0.50 - 0.545) / 0.455)

    def test_high_agreement_beats_the_threshold(self) -> None:
        a = ["good"] * 45 + ["bad"] * 45 + ["good"] * 10
        b = ["good"] * 45 + ["bad"] * 45 + ["bad"] * 10
        assert cohens_kappa(a, b) > 0.70

    def test_kappa_is_symmetric(self) -> None:
        a = ["a", "b", "a", "c"]
        b = ["a", "b", "c", "c"]
        assert cohens_kappa(a, b) == pytest.approx(cohens_kappa(b, a))

    def test_degenerate_identical_constant_labelling_is_one(self) -> None:
        assert cohens_kappa(["x"] * 5, ["x"] * 5) == 1.0

    def test_degenerate_opposing_constant_labelling_is_zero(self) -> None:
        assert cohens_kappa(["x"] * 5, ["y"] * 5) == 0.0

    def test_more_than_two_labels(self) -> None:
        a = ["low", "mid", "high", "low", "mid"]
        b = ["low", "mid", "high", "mid", "mid"]
        assert 0.0 < cohens_kappa(a, b) < 1.0


class TestValidation:
    def test_unequal_lengths_are_rejected(self) -> None:
        with pytest.raises(AgreementError, match="unequal lengths"):
            cohens_kappa(["a"], ["a", "b"])

    def test_empty_sample_is_rejected(self) -> None:
        with pytest.raises(AgreementError, match="empty sample"):
            cohens_kappa([], [])


class TestConfusionMatrix:
    def test_pairs_are_counted(self) -> None:
        matrix = confusion_matrix(["a", "a", "b"], ["a", "b", "b"])
        assert matrix[("a", "a")] == 1
        assert matrix[("a", "b")] == 1
        assert matrix[("b", "b")] == 1


class TestAgreementReport:
    def test_passing_round_is_accepted(self) -> None:
        a = ["good"] * 45 + ["bad"] * 45 + ["good"] * 10
        b = ["good"] * 45 + ["bad"] * 45 + ["bad"] * 10
        report = score_agreement(a, b)
        assert report.passed
        assert "ACCEPTED" in report.summary()

    def test_failing_round_is_rejected(self) -> None:
        report = score_agreement(["a", "b", "a", "b"], ["a", "a", "b", "b"])
        assert not report.passed
        assert "REJECTED" in report.summary()

    def test_threshold_is_configurable(self) -> None:
        a = ["a", "a", "a", "b"]
        b = ["a", "a", "b", "b"]
        assert not score_agreement(a, b, threshold=0.99).passed
        assert score_agreement(a, b, threshold=0.1).passed

    def test_labels_are_collected_and_sorted(self) -> None:
        report = score_agreement(["b", "a"], ["a", "c"])
        assert report.labels == ("a", "b", "c")

    def test_item_count_is_reported(self) -> None:
        assert score_agreement(["a"] * 7, ["a"] * 7).items == 7

    @pytest.mark.parametrize(
        ("kappa_pair", "expected"),
        [
            ((["a", "b"], ["a", "b"]), "almost perfect"),
            ((["a", "a", "b", "b"], ["b", "b", "a", "a"]), "poor"),
        ],
    )
    def test_interpretation_bands(
        self, kappa_pair: tuple[list[str], list[str]], expected: str
    ) -> None:
        assert score_agreement(*kappa_pair).interpretation == expected
