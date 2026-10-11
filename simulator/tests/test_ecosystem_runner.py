import csv

import pytest

from paleosphere.ecosystem import COLUMNS, main, parse_seeds, run_series


def test_parse_seeds():
    assert parse_seeds("0-3,9") == [0, 1, 2, 3, 9]


def test_series_rows_and_determinism():
    a = run_series(3, ticks=600, every=100)
    assert [r["tick"] for r in a] == [0, 100, 200, 300, 400, 500, 600]
    assert set(a[0]) == set(COLUMNS)
    assert a == run_series(3, ticks=600, every=100)


def test_requires_reproduction_config():
    with pytest.raises(ValueError, match="reproduction"):
        run_series(0, config="map_a", ticks=10)


def test_cli_writes_csv(tmp_path):
    out = tmp_path / "pop.csv"
    main(["--seeds", "1-2", "--ticks", "200", "--every", "100", "--workers", "1",
          "--out", str(out)])
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert len(rows) == 6 and rows[0].keys() == set(COLUMNS)
