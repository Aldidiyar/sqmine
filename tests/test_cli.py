from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from sqmine.cli import EXIT_ERROR, EXIT_GATE_FAILED, EXIT_OK, main

CRM_CSV = """TRX_ID,CLIENT_NO,DT_OPEN,DURATION_MIN,WAIT_SEC,CHANNEL,SERVICE,STATUS,OPERATOR,COMMENT
T-1,CL-100,2026-03-02T09:00:00,7.5,45,office,card-dispute,closed,OP-9,fine
T-2,CL-101,2026-03-02T10:15:00,3,120,call,balance,complaint,OP-7,ring me
T-3,CL-100,2026-03-05T11:00:00,12,0,chat,card-dispute,ok,,
"""

LABELS_GOOD = "item,ann_a,ann_b\n" + "".join(
    f"i{i},{'good' if i < 45 else 'bad'},{'good' if i < 45 else 'bad'}\n"
    for i in range(90)
)
LABELS_BAD = "item,ann_a,ann_b\n" + "".join(
    f"i{i},{'good' if i % 2 else 'bad'},{'bad' if i % 2 else 'good'}\n" for i in range(20)
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "crm.csv").write_text(CRM_CSV, encoding="utf-8")
    (tmp_path / "key.txt").write_bytes(b"integration-test-key")
    (tmp_path / "labels_good.csv").write_text(LABELS_GOOD, encoding="utf-8")
    (tmp_path / "labels_bad.csv").write_text(LABELS_BAD, encoding="utf-8")
    return tmp_path


def run(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(argv, out=out, err=err)
    return code, out.getvalue(), err.getvalue()


class TestParser:
    def test_no_command_exits(self) -> None:
        with pytest.raises(SystemExit):
            main([])

    def test_version_exits_zero(self) -> None:
        with pytest.raises(SystemExit) as excinfo:
            main(["--version"])
        assert excinfo.value.code == 0

    def test_unknown_adapter_is_rejected_by_the_parser(self) -> None:
        with pytest.raises(SystemExit):
            main(
                [
                    "ingest",
                    "x.csv",
                    "--adapter",
                    "nope",
                    "--tenant",
                    "t",
                    "--key-file",
                    "k",
                ]
            )


class TestIngest:
    def test_episodes_are_written_as_json_lines(self, workspace: Path) -> None:
        out_file = workspace / "episodes.jsonl"
        code, _, err = run(
            [
                "ingest",
                str(workspace / "crm.csv"),
                "--adapter",
                "crm-csv",
                "--tenant",
                "pilot",
                "--key-file",
                str(workspace / "key.txt"),
                "--out",
                str(out_file),
            ]
        )
        assert code == EXIT_OK
        lines = out_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3
        assert json.loads(lines[0])["tenant_id"] == "pilot"
        assert "3/3 rows accepted" in err

    def test_output_defaults_to_stdout(self, workspace: Path) -> None:
        code, out, _ = run(
            [
                "ingest",
                str(workspace / "crm.csv"),
                "--adapter",
                "crm-csv",
                "--tenant",
                "pilot",
                "--key-file",
                str(workspace / "key.txt"),
            ]
        )
        assert code == EXIT_OK
        assert len(out.strip().splitlines()) == 3

    def test_raw_identifiers_are_absent_from_the_output(self, workspace: Path) -> None:
        _, out, _ = run(
            [
                "ingest",
                str(workspace / "crm.csv"),
                "--adapter",
                "crm-csv",
                "--tenant",
                "pilot",
                "--key-file",
                str(workspace / "key.txt"),
            ]
        )
        assert "CL-100" not in out and "OP-9" not in out

    def test_rejected_rows_are_reported_on_stderr(self, workspace: Path) -> None:
        broken = workspace / "broken.csv"
        broken.write_text(CRM_CSV + "T-4,CL-1,nope,5,0,call,x,ok,,\n", encoding="utf-8")
        code, _, err = run(
            [
                "ingest",
                str(broken),
                "--adapter",
                "crm-csv",
                "--tenant",
                "pilot",
                "--key-file",
                str(workspace / "key.txt"),
            ]
        )
        assert code == EXIT_OK
        assert "1 rejected" in err and "row 3" in err

    def test_acceptance_gate_fails_the_run(self, workspace: Path) -> None:
        broken = workspace / "broken.csv"
        broken.write_text(CRM_CSV + "T-4,CL-1,nope,5,0,call,x,ok,,\n", encoding="utf-8")
        code, _, err = run(
            [
                "ingest",
                str(broken),
                "--adapter",
                "crm-csv",
                "--tenant",
                "pilot",
                "--key-file",
                str(workspace / "key.txt"),
                "--fail-under",
                "0.9",
            ]
        )
        assert code == EXIT_GATE_FAILED
        assert "below the required" in err

    def test_missing_key_file_is_reported(self, workspace: Path) -> None:
        code, _, err = run(
            [
                "ingest",
                str(workspace / "crm.csv"),
                "--adapter",
                "crm-csv",
                "--tenant",
                "pilot",
                "--key-file",
                str(workspace / "absent.txt"),
            ]
        )
        assert code == EXIT_ERROR
        assert "error:" in err


class TestFeatures:
    def test_csv_table_is_produced(self, workspace: Path) -> None:
        episodes = workspace / "episodes.jsonl"
        run(
            [
                "ingest",
                str(workspace / "crm.csv"),
                "--adapter",
                "crm-csv",
                "--tenant",
                "pilot",
                "--key-file",
                str(workspace / "key.txt"),
                "--out",
                str(episodes),
            ]
        )
        features = workspace / "features.csv"
        code, _, _ = run(["features", str(episodes), "--out", str(features)])
        assert code == EXIT_OK
        lines = features.read_text(encoding="utf-8").strip().splitlines()
        assert lines[0].startswith("episode_id,")
        assert len(lines) == 4

    def test_stats_go_to_stderr(self, workspace: Path) -> None:
        episodes = workspace / "episodes.jsonl"
        run(
            [
                "ingest",
                str(workspace / "crm.csv"),
                "--adapter",
                "crm-csv",
                "--tenant",
                "pilot",
                "--key-file",
                str(workspace / "key.txt"),
                "--out",
                str(episodes),
            ]
        )
        code, _, err = run(["features", str(episodes), "--stats"])
        assert code == EXIT_OK
        assert "escalation_rate" in err


class TestAgreement:
    def test_passing_round_exits_zero(self, workspace: Path) -> None:
        code, out, _ = run(
            [
                "agreement",
                str(workspace / "labels_good.csv"),
                "--col-a",
                "ann_a",
                "--col-b",
                "ann_b",
            ]
        )
        assert code == EXIT_OK
        assert "ACCEPTED" in out

    def test_failing_round_exits_two(self, workspace: Path) -> None:
        code, out, _ = run(
            [
                "agreement",
                str(workspace / "labels_bad.csv"),
                "--col-a",
                "ann_a",
                "--col-b",
                "ann_b",
            ]
        )
        assert code == EXIT_GATE_FAILED
        assert "REJECTED" in out

    def test_missing_column_is_reported(self, workspace: Path) -> None:
        code, _, err = run(
            [
                "agreement",
                str(workspace / "labels_good.csv"),
                "--col-a",
                "ann_a",
                "--col-b",
                "absent",
            ]
        )
        assert code == EXIT_ERROR
        assert "not found" in err

    def test_empty_file_is_reported(self, workspace: Path) -> None:
        empty = workspace / "empty.csv"
        empty.write_text("item,ann_a,ann_b\n", encoding="utf-8")
        code, _, err = run(
            ["agreement", str(empty), "--col-a", "ann_a", "--col-b", "ann_b"]
        )
        assert code == EXIT_ERROR
        assert "no rows" in err


def test_full_pipeline_end_to_end(workspace: Path) -> None:
    """ingest -> features, exercised exactly as the README documents it."""
    episodes = workspace / "episodes.jsonl"
    features = workspace / "features.csv"

    assert (
        run(
            [
                "ingest",
                str(workspace / "crm.csv"),
                "--adapter",
                "crm-csv",
                "--tenant",
                "pilot",
                "--key-file",
                str(workspace / "key.txt"),
                "--out",
                str(episodes),
            ]
        )[0]
        == EXIT_OK
    )
    assert run(["features", str(episodes), "--out", str(features)])[0] == EXIT_OK

    rows = features.read_text(encoding="utf-8").strip().splitlines()
    header = rows[0].split(",")
    repeat_index = header.index("is_repeat_contact")
    # CL-100 appears on 2 and 5 March, so the later episode is a repeat contact.
    assert [r.split(",")[repeat_index] for r in rows[1:]].count("1") == 1
