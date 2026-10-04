import argparse
import sys
import time
from typing import Sequence
from lob.model import MatchResult, CancelResult, Trade
from lob.engine import empty_book, process_order
from lob.io import read_orders_csv, write_trades_csv, format_book_snapshot, TICK_FACTOR


def run_replay(
    input_path: str,
    output_trades_path: str | None = None,
    output_snapshots_path: str | None = None,
    tick_factor: int = TICK_FACTOR,
    quiet: bool = False,
) -> int:
    """Replay an order file against the engine sequentially."""
    book = empty_book()
    all_trades: list[Trade] = []
    processed_count = 0
    start_time = time.perf_counter()

    with open(input_path, "r", encoding="utf-8") as f:
        orders = list(read_orders_csv(f, tick_factor=tick_factor))

    if not quiet:
        print(f"Loaded {len(orders)} order events from '{input_path}'. Starting replay...")

    for order in orders:
        res = process_order(book, order)
        book = res.book
        processed_count += 1

        if isinstance(res, MatchResult) and res.trades:
            all_trades.extend(res.trades)

    elapsed = time.perf_counter() - start_time
    ops_per_sec = processed_count / elapsed if elapsed > 0 else 0

    if not quiet:
        print(f"Replay finished in {elapsed * 1000:.2f} ms ({ops_per_sec:,.0f} ops/sec)")
        print(f"Total processed events: {processed_count}")
        print(f"Total executed trades: {len(all_trades)}")
        print("\nFinal Book State:")
        print(format_book_snapshot(book, depth=5, tick_factor=tick_factor))

    if output_trades_path:
        with open(output_trades_path, "w", encoding="utf-8", newline="") as f:
            write_trades_csv(all_trades, f, tick_factor=tick_factor)
        if not quiet:
            print(f"Wrote {len(all_trades)} trades to '{output_trades_path}'")

    if output_snapshots_path:
        with open(output_snapshots_path, "w", encoding="utf-8") as f:
            f.write(format_book_snapshot(book, depth=20, tick_factor=tick_factor))
        if not quiet:
            print(f"Wrote final book snapshot to '{output_snapshots_path}'")

    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lob",
        description="LOB - Limit Order Book & Matching Engine CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Replay subcommand
    replay_parser = subparsers.add_parser("replay", help="Replay order stream from CSV file")
    replay_parser.add_argument(
        "--input", "-i", required=True, help="Input CSV file path containing order events"
    )
    replay_parser.add_argument(
        "--output-trades", "-t", default=None, help="Output CSV file path for executed trades"
    )
    replay_parser.add_argument(
        "--output-snapshots", "-s", default=None, help="Output text file path for final order book snapshot"
    )
    replay_parser.add_argument(
        "--tick-factor", type=int, default=TICK_FACTOR, help="Tick multiplier (default 100)"
    )
    replay_parser.add_argument(
        "--quiet", "-q", action="store_true", help="Suppress verbose output"
    )

    args = parser.parse_args(argv)

    if args.command == "replay":
        return run_replay(
            input_path=args.input,
            output_trades_path=args.output_trades,
            output_snapshots_path=args.output_snapshots,
            tick_factor=args.tick_factor,
            quiet=args.quiet,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
