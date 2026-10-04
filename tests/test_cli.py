import tempfile
from pathlib import Path
from lob.cli import main, run_replay


SAMPLE_CSV = """timestamp,action,order_id,side,price,quantity
1,LIMIT,O1,BUY,100.00,10
2,LIMIT,O2,SELL,101.00,5
3,LIMIT,O3,BUY,101.00,3
4,MARKET,O4,SELL,0,4
5,CANCEL,O1,BUY,0,0
"""


def test_cli_replay_flow(tmp_path: Path) -> None:
    input_file = tmp_path / "orders.csv"
    trades_file = tmp_path / "trades.csv"
    snapshots_file = tmp_path / "snapshots.txt"

    input_file.write_text(SAMPLE_CSV, encoding="utf-8")

    code = main([
        "replay",
        "--input", str(input_file),
        "--output-trades", str(trades_file),
        "--output-snapshots", str(snapshots_file),
        "--quiet",
    ])
    assert code == 0

    assert trades_file.exists()
    trades_content = trades_file.read_text(encoding="utf-8")
    assert "trade_id" in trades_content
    assert "O3" in trades_content  # Match between O3 and O2
    assert "O4" in trades_content  # Market sell match

    assert snapshots_file.exists()
    snapshot_content = snapshots_file.read_text(encoding="utf-8")
    assert "ORDER BOOK SNAPSHOT" in snapshot_content
