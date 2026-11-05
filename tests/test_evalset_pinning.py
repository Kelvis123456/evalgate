import json

from evalgate.cli import main
from evalgate.evalset import fingerprint

SET = (
    '{"id": "a", "question": "size?", "gold_ids": ["p1"], "gold_fact": "256 KB"}\n'
    '{"id": "b", "question": "when?", "gold_ids": ["p2"], "gold_fact": "7 days"}\n'
)


def test_baseline_records_evalset_hash_and_count(tmp_path):
    ev = tmp_path / "q.jsonl"
    ev.write_text(SET, encoding="utf-8")
    out = tmp_path / "b.json"
    assert main(["baseline", "--evalset", str(ev), "--baseline", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["evalset"] == {"sha256": fingerprint(SET), "questions": 2}


def test_run_fails_with_exit_2_when_questions_are_deleted(tmp_path, capsys):
    ev = tmp_path / "q.jsonl"
    ev.write_text(SET, encoding="utf-8")
    base = tmp_path / "b.json"
    assert main(["baseline", "--evalset", str(ev), "--baseline", str(base)]) == 0
    assert main(["run", "--evalset", str(ev), "--baseline", str(base)]) == 0
    ev.write_text(SET.splitlines()[0] + "\n", encoding="utf-8")  # drop the hard question
    capsys.readouterr()
    assert main(["run", "--evalset", str(ev), "--baseline", str(base)]) == 2
    err = capsys.readouterr().err
    assert "eval set changed" in err and "2 questions" in err and "1 questions" in err
    assert fingerprint(SET)[:12] in err


def test_line_endings_and_blank_lines_do_not_change_the_hash():
    assert fingerprint(SET) == fingerprint(SET.replace("\n", "\r\n") + "\n\n")
    assert fingerprint(SET) != fingerprint(SET.replace("7 days", "8 days"))


def test_baseline_without_evalset_record_is_rejected(tmp_path, capsys):
    base = tmp_path / "old.json"
    base.write_text(json.dumps({"metrics": {"hit_at_k": 0.1}}), encoding="utf-8")
    assert main(["run", "--baseline", str(base)]) == 2
    assert "does not record its eval set" in capsys.readouterr().err
