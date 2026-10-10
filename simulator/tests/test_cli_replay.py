from paleosphere.logging.replay import read_replay
from paleosphere.run import main


def test_cli_summary_runs(capsys):
    result = main(["--seed", "42", "--ticks", "200"])
    out = capsys.readouterr().out
    assert "kills" in out
    assert result["ticks"] == 200
    assert result["steps_per_sec"] > 0


def test_cli_random_policy():
    result = main(["--seed", "1", "--ticks", "100", "--predator", "random", "--json"])
    assert result["predator_policy"] == "random-predatoraction"


def test_replay_roundtrip(tmp_path):
    path = tmp_path / "r.jsonl"
    main(["--seed", "3", "--ticks", "50", "--replay", str(path), "--replay-every", "10"])
    header, frames = read_replay(path)
    assert header["type"] == "header" and header["seed"] == 3
    ticks = [f["snapshot"]["tick"] for f in frames]
    assert ticks == [0, 10, 20, 30, 40, 50]
    assert len(frames[0]["snapshot"]["dinos"]) == 9


def test_steps_per_second_report():
    result = main(["--seed", "42", "--ticks", "2000", "--json"])
    rate = result["steps_per_sec"]
    print(f"steps/s = {rate}")
    if rate < 3000:
        import warnings

        warnings.warn(f"simulation slower than 3000 steps/s target: {rate}", stacklevel=1)
