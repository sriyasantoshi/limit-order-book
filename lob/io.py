import csv
from typing import TextIO, Iterator, Sequence
from lob.types import Side, OrderType, Price, Quantity, OrderId, Timestamp
from lob.model import Order, Trade, OrderBook

TICK_FACTOR = 100  # Default multiplier: 1.00 currency unit = 100 ticks


def parse_price(val: str | float | int, tick_factor: int = TICK_FACTOR) -> Price:
    """Parse string/float price to integer ticks."""
    if isinstance(val, int):
        return val
    return int(round(float(val) * tick_factor))


def format_price(ticks: Price | None, tick_factor: int = TICK_FACTOR) -> str:
    """Format integer ticks to decimal string."""
    if ticks is None:
        return "N/A"
    return f"{ticks / tick_factor:.2f}"


def read_orders_csv(
    file_obj: TextIO,
    tick_factor: int = TICK_FACTOR,
) -> Iterator[Order]:
    """
    Read order events from a CSV stream.
    Expected header: timestamp,action,order_id,side,price,quantity
    """
    reader = csv.DictReader(file_obj)
    for row in reader:
        action_str = row["action"].strip().upper()
        order_type = OrderType(action_str)

        ts = int(row["timestamp"].strip())
        order_id = row["order_id"].strip()

        side_str = row.get("side", "BUY").strip().upper()
        side = Side(side_str) if side_str in ("BUY", "SELL") else Side.BUY

        raw_price = row.get("price", "0").strip()
        price = parse_price(raw_price, tick_factor=tick_factor) if raw_price else 0

        raw_qty = row.get("quantity", "0").strip()
        qty = int(raw_qty) if raw_qty else 0

        yield Order(
            order_id=order_id,
            side=side,
            price=price,
            quantity=qty,
            remaining_qty=qty,
            timestamp=ts,
            order_type=order_type,
        )


def write_trades_csv(
    trades: Sequence[Trade],
    file_obj: TextIO,
    tick_factor: int = TICK_FACTOR,
) -> None:
    """Write executed trades to a CSV stream."""
    writer = csv.writer(file_obj)
    writer.writerow([
        "timestamp",
        "trade_id",
        "maker_order_id",
        "taker_order_id",
        "taker_side",
        "price",
        "quantity",
    ])
    for t in trades:
        writer.writerow([
            t.timestamp,
            t.trade_id,
            t.maker_order_id,
            t.taker_order_id,
            t.taker_side.value,
            format_price(t.price, tick_factor=tick_factor),
            t.quantity,
        ])


def format_book_snapshot(
    book: OrderBook,
    depth: int = 5,
    tick_factor: int = TICK_FACTOR,
) -> str:
    """Format an OrderBook snapshot as a human-readable string."""
    lines: list[str] = ["=== ORDER BOOK SNAPSHOT ==="]

    lines.append(f"Best Bid: {format_price(book.best_bid, tick_factor)} | Best Ask: {format_price(book.best_ask, tick_factor)} | Spread: {format_price(book.spread, tick_factor)}")
    lines.append(f"Total Bid Vol: {book.total_bid_volume} | Total Ask Vol: {book.total_ask_volume}")
    lines.append("-" * 40)

    lines.append(" ASKS (Lowest First):")
    if not book.asks:
        lines.append("   (Empty)")
    else:
        for level in book.asks[:depth]:
            p_str = format_price(level.price, tick_factor)
            lines.append(f"   Price: {p_str:>8} | Vol: {level.total_volume:>6} | Orders: {len(level.orders)}")

    lines.append("-" * 40)
    lines.append(" BIDS (Highest First):")
    if not book.bids:
        lines.append("   (Empty)")
    else:
        for level in book.bids[:depth]:
            p_str = format_price(level.price, tick_factor)
            lines.append(f"   Price: {p_str:>8} | Vol: {level.total_volume:>6} | Orders: {len(level.orders)}")

    lines.append("===========================")
    return "\n".join(lines)
