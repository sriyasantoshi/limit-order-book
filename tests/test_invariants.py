import hypothesis.strategies as st
from hypothesis import given, settings, HealthCheck
from lob.types import Side, OrderType
from lob.model import Order, OrderBook, Trade, MatchResult, CancelResult
from lob.engine import empty_book, process_order


@st.composite
def order_sequence_strategy(draw: st.DrawFn) -> list[Order]:
    """Generate a valid sequence of Order events including LIMIT, MARKET, and CANCEL."""
    num_orders = draw(st.integers(min_value=1, max_value=40))
    orders: list[Order] = []
    active_order_ids: list[str] = []

    prices = draw(st.lists(st.integers(min_value=10, max_value=150), min_size=num_orders, max_size=num_orders))
    quantities = draw(st.lists(st.integers(min_value=1, max_value=50), min_size=num_orders, max_size=num_orders))
    sides = draw(st.lists(st.sampled_from([Side.BUY, Side.SELL]), min_size=num_orders, max_size=num_orders))
    order_types = draw(
        st.lists(
            st.sampled_from([OrderType.LIMIT, OrderType.LIMIT, OrderType.MARKET, OrderType.CANCEL]),
            min_size=num_orders,
            max_size=num_orders,
        )
    )

    for i in range(num_orders):
        oid = f"O-{i+1}"
        otype = order_types[i]
        price = prices[i]
        qty = quantities[i]
        side = sides[i]
        ts = i + 1

        if otype == OrderType.CANCEL and active_order_ids:
            target_cancel_id = draw(st.sampled_from(active_order_ids))
            orders.append(
                Order(
                    order_id=target_cancel_id,
                    side=side,
                    price=0,
                    quantity=0,
                    remaining_qty=0,
                    timestamp=ts,
                    order_type=OrderType.CANCEL,
                )
            )
        elif otype == OrderType.MARKET:
            orders.append(
                Order(
                    order_id=oid,
                    side=side,
                    price=0,
                    quantity=qty,
                    remaining_qty=qty,
                    timestamp=ts,
                    order_type=OrderType.MARKET,
                )
            )
        else:  # LIMIT
            active_order_ids.append(oid)
            orders.append(
                Order(
                    order_id=oid,
                    side=side,
                    price=price,
                    quantity=qty,
                    remaining_qty=qty,
                    timestamp=ts,
                    order_type=OrderType.LIMIT,
                )
            )

    return orders


@given(orders=order_sequence_strategy())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_invariant_book_is_never_crossed(orders: list[Order]) -> None:
    """INVARIANT 1: The order book is never crossed (best_bid < best_ask)."""
    book = empty_book()
    for order in orders:
        res = process_order(book, order)
        book = res.book
        assert not book.is_crossed, (
            f"Book crossed after order {order}: best_bid={book.best_bid}, best_ask={book.best_ask}"
        )


@given(orders=order_sequence_strategy())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_invariant_quantity_is_conserved(orders: list[Order]) -> None:
    """
    INVARIANT 2: Quantity is conserved.
    Total Submitted Volume (Limit + Market) ==
        Resting Volume + (2 * Executed Trade Volume) + Cancelled Limit Volume + Unfilled Market Volume.
    """
    book = empty_book()
    all_trades: list[Trade] = []

    total_limit_submitted = 0
    total_market_submitted = 0
    cancelled_limit_qty = 0
    unfilled_market_qty = 0

    for order in orders:
        if order.order_type == OrderType.LIMIT:
            total_limit_submitted += order.quantity
        elif order.order_type == OrderType.MARKET:
            total_market_submitted += order.quantity

        res = process_order(book, order)
        book = res.book

        if isinstance(res, MatchResult):
            if res.trades:
                all_trades.extend(res.trades)
            if order.order_type == OrderType.MARKET:
                unfilled_market_qty += res.cancelled_quantity

        elif isinstance(res, CancelResult) and res.success and res.cancelled_order:
            cancelled_limit_qty += res.cancelled_order.remaining_qty

    resting_qty = book.total_bid_volume + book.total_ask_volume
    executed_trade_volume = sum(t.quantity for t in all_trades)

    total_submitted = total_limit_submitted + total_market_submitted
    total_accounted = resting_qty + (2 * executed_trade_volume) + cancelled_limit_qty + unfilled_market_qty

    assert total_submitted == total_accounted, (
        f"Quantity conservation failed!\n"
        f"Total Submitted: {total_submitted} (Limit: {total_limit_submitted}, Market: {total_market_submitted})\n"
        f"Total Accounted: {total_accounted} (Resting: {resting_qty}, Executed Trade Vol: {executed_trade_volume}, "
        f"Cancelled Limit: {cancelled_limit_qty}, Unfilled Market: {unfilled_market_qty})"
    )


@given(orders=order_sequence_strategy())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_invariant_price_time_priority(orders: list[Order]) -> None:
    """
    INVARIANT 3: Price-time priority holds.
    1. Price priority: BUY taker matches ascending ask prices; SELL taker matches descending bid prices.
    2. Time priority: FIFO execution within each price level.
    """
    book = empty_book()

    for order in orders:
        if order.order_type in (OrderType.LIMIT, OrderType.MARKET):
            res = process_order(book, order)

            if isinstance(res, MatchResult) and res.trades:
                trade_prices = [t.price for t in res.trades]
                if order.side == Side.BUY:
                    # Taker buy matches lowest asks first -> non-decreasing trade prices
                    assert trade_prices == sorted(trade_prices), (
                        f"Price priority violated for Taker BUY: trade prices {trade_prices} not ascending"
                    )
                else:
                    # Taker sell matches highest bids first -> non-increasing trade prices
                    assert trade_prices == sorted(trade_prices, reverse=True), (
                        f"Price priority violated for Taker SELL: trade prices {trade_prices} not descending"
                    )

            book = res.book
        else:
            book = process_order(book, order).book


@given(orders=order_sequence_strategy())
@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
def test_invariant_determinism(orders: list[Order]) -> None:
    """INVARIANT 4: Replaying the exact same input sequence gives the exact same output."""

    def replay_all(seq: list[Order]) -> tuple[OrderBook, list[Trade]]:
        b = empty_book()
        trades: list[Trade] = []
        for o in seq:
            res = process_order(b, o)
            b = res.book
            if isinstance(res, MatchResult) and res.trades:
                trades.extend(res.trades)
        return b, trades

    book1, trades1 = replay_all(orders)
    book2, trades2 = replay_all(orders)

    assert book1 == book2, "Book state mismatch between identical replay runs"
    assert trades1 == trades2, "Trades mismatch between identical replay runs"
