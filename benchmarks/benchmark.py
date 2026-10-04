import random
import time
from typing import Sequence
import numpy as np
from lob.types import Side, OrderType
from lob.model import Order, OrderBook
from lob.engine import empty_book, process_order


def generate_benchmark_orders(num_orders: int = 50000, seed: int = 42) -> list[Order]:
    """Generate a realistic stream of Limit, Market, and Cancel orders around a midpoint price."""
    rnd = random.Random(seed)
    orders: list[Order] = []
    active_ids: list[str] = []

    midpoint = 10000  # $100.00 base price

    for i in range(1, num_orders + 1):
        oid = f"ORD-{i}"
        side = rnd.choice([Side.BUY, Side.SELL])
        r = rnd.random()

        if r < 0.15 and active_ids:
            # Cancel order (15% chance)
            cancel_id = rnd.choice(active_ids)
            orders.append(
                Order(
                    order_id=cancel_id,
                    side=side,
                    price=0,
                    quantity=0,
                    remaining_qty=0,
                    timestamp=i,
                    order_type=OrderType.CANCEL,
                )
            )
        elif r < 0.30:
            # Market order (15% chance)
            qty = rnd.randint(1, 50)
            orders.append(
                Order(
                    order_id=oid,
                    side=side,
                    price=0,
                    quantity=qty,
                    remaining_qty=qty,
                    timestamp=i,
                    order_type=OrderType.MARKET,
                )
            )
        else:
            # Limit order (70% chance)
            qty = rnd.randint(1, 100)
            offset = rnd.randint(-50, 50)
            price = max(10, midpoint + offset)

            active_ids.append(oid)
            if len(active_ids) > 1000:
                active_ids.pop(0)

            orders.append(
                Order(
                    order_id=oid,
                    side=side,
                    price=price,
                    quantity=qty,
                    remaining_qty=qty,
                    timestamp=i,
                    order_type=OrderType.LIMIT,
                )
            )

    return orders


def run_benchmark(num_orders: int = 50000, warmup: int = 1000) -> dict[str, float]:
    """Run per-order latency and throughput benchmark."""
    print(f"Generating {num_orders} synthetic order events...")
    orders = generate_benchmark_orders(num_orders=num_orders)

    book = empty_book()

    # Warmup
    for o in orders[:warmup]:
        res = process_order(book, o)
        book = res.book

    test_orders = orders[warmup:]
    book = empty_book()

    latencies_ns: list[int] = []

    print(f"Executing benchmark on {len(test_orders)} orders...")
    total_start = time.perf_counter_ns()

    for o in test_orders:
        t0 = time.perf_counter_ns()
        res = process_order(book, o)
        t1 = time.perf_counter_ns()

        book = res.book
        latencies_ns.append(t1 - t0)

    total_end = time.perf_counter_ns()

    total_elapsed_sec = (total_end - total_start) / 1e9
    ops_sec = len(test_orders) / total_elapsed_sec

    latencies_us = np.array(latencies_ns, dtype=np.float64) / 1000.0

    p50 = float(np.percentile(latencies_us, 50))
    p90 = float(np.percentile(latencies_us, 90))
    p99 = float(np.percentile(latencies_us, 99))
    p99_9 = float(np.percentile(latencies_us, 99.9))
    mean_lat = float(np.mean(latencies_us))
    max_lat = float(np.max(latencies_us))

    print("\n" + "=" * 50)
    print(" LOB MATCHING ENGINE BENCHMARK RESULTS")
    print("=" * 50)
    print(f"Total Orders Processed : {len(test_orders):,}")
    print(f"Total Time Elapsed     : {total_elapsed_sec:.4f} s")
    print(f"Throughput             : {ops_sec:,.2f} orders/sec")
    print("-" * 50)
    print(" Per-Order Latency Distribution (microseconds):")
    print(f"   Mean Latency  : {mean_lat:8.2f} µs")
    print(f"   p50 (Median)  : {p50:8.2f} µs")
    print(f"   p90           : {p90:8.2f} µs")
    print(f"   p99           : {p99:8.2f} µs")
    print(f"   p99.9         : {p99_9:8.2f} µs")
    print(f"   Max Latency   : {max_lat:8.2f} µs")
    print("=" * 50 + "\n")

    return {
        "ops_sec": ops_sec,
        "mean_us": mean_lat,
        "p50_us": p50,
        "p90_us": p90,
        "p99_us": p99,
        "p99_9_us": p99_9,
        "max_us": max_lat,
    }


if __name__ == "__main__":
    run_benchmark(num_orders=50000)
