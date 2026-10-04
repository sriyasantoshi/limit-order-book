from dataclasses import replace
from typing import Sequence
from lob.types import Side, OrderType, Price, Quantity, OrderId
from lob.model import (
    Order,
    PriceLevel,
    OrderBook,
    Trade,
    MatchResult,
    CancelResult,
)

def empty_book() -> OrderBook:
    """Create a new empty OrderBook."""
    return OrderBook(bids=(), asks=(), order_index={})


def process_order(book: OrderBook, order: Order) -> MatchResult | CancelResult:
    """
    Pure entrypoint to process an incoming order or cancel against the book.
    
    Returns a MatchResult (for LIMIT or MARKET orders) or CancelResult (for CANCEL orders).
    No side effects or mutations are performed on book or order.
    """
    if order.order_type == OrderType.CANCEL:
        return cancel_order(book, order.order_id)
    elif order.order_type == OrderType.MARKET:
        return match_market_order(book, order)
    elif order.order_type == OrderType.LIMIT:
        return match_limit_order(book, order)
    else:
        raise ValueError(f"Unknown order type: {order.order_type}")


def cancel_order(book: OrderBook, order_id: OrderId) -> CancelResult:
    """Purely remove an order from the book by order_id."""
    loc = book.order_index.get(order_id)
    if loc is None:
        return CancelResult(book=book, cancelled_order=None, success=False)

    side, price = loc
    levels = book.bids if side == Side.BUY else book.asks

    new_levels: list[PriceLevel] = []
    cancelled_order: Order | None = None

    for level in levels:
        if level.price == price:
            new_orders: list[Order] = []
            for o in level.orders:
                if o.order_id == order_id:
                    cancelled_order = o
                else:
                    new_orders.append(o)
            if new_orders:
                new_levels.append(replace(level, orders=tuple(new_orders)))
        else:
            new_levels.append(level)

    new_index = dict(book.order_index)
    new_index.pop(order_id, None)

    if side == Side.BUY:
        new_book = replace(book, bids=tuple(new_levels), order_index=new_index)
    else:
        new_book = replace(book, asks=tuple(new_levels), order_index=new_index)

    return CancelResult(
        book=new_book,
        cancelled_order=cancelled_order,
        success=cancelled_order is not None,
    )


def match_limit_order(book: OrderBook, incoming: Order) -> MatchResult:
    """Match a LIMIT order against resting orders, placing any remaining quantity on the book."""
    if incoming.quantity <= 0 or incoming.remaining_qty <= 0:
        raise ValueError("Order quantity must be positive")

    return _match_order(book, incoming, is_market=False)


def match_market_order(book: OrderBook, incoming: Order) -> MatchResult:
    """Match a MARKET order against resting orders, cancelling any unfulfilled quantity."""
    if incoming.quantity <= 0 or incoming.remaining_qty <= 0:
        raise ValueError("Order quantity must be positive")

    return _match_order(book, incoming, is_market=True)


def _match_order(book: OrderBook, incoming: Order, is_market: bool) -> MatchResult:
    rem_taker_qty = incoming.remaining_qty
    taker_side = incoming.side
    counter_levels = list(book.asks if taker_side == Side.BUY else book.bids)

    trades: list[Trade] = []
    new_index = dict(book.order_index)
    updated_counter_levels: list[PriceLevel] = []

    trade_seq = 0

    for level in counter_levels:
        if rem_taker_qty <= 0:
            updated_counter_levels.append(level)
            continue

        # Check price match condition for LIMIT orders
        if not is_market:
            if taker_side == Side.BUY and level.price > incoming.price:
                # Ask price is higher than buy limit price
                updated_counter_levels.append(level)
                continue
            elif taker_side == Side.SELL and level.price < incoming.price:
                # Bid price is lower than sell limit price
                updated_counter_levels.append(level)
                continue

        # Match against FIFO orders at this price level
        new_level_orders: list[Order] = []
        for maker in level.orders:
            if rem_taker_qty <= 0:
                new_level_orders.append(maker)
                continue

            fill_qty = min(rem_taker_qty, maker.remaining_qty)
            trade_seq += 1

            trade = Trade(
                trade_id=f"T-{incoming.order_id}-{trade_seq}",
                maker_order_id=maker.order_id,
                taker_order_id=incoming.order_id,
                price=level.price,  # Price-time priority: Maker price rules
                quantity=fill_qty,
                taker_side=taker_side,
                timestamp=incoming.timestamp,
            )
            trades.append(trade)

            rem_taker_qty -= fill_qty
            updated_maker = maker.with_filled(fill_qty)

            if updated_maker.remaining_qty > 0:
                new_level_orders.append(updated_maker)
            else:
                new_index.pop(maker.order_id, None)

        if new_level_orders:
            updated_counter_levels.append(replace(level, orders=tuple(new_level_orders)))

    # Reconstruct counter side of order book
    if taker_side == Side.BUY:
        asks_tuple = tuple(updated_counter_levels)
        bids_tuple = book.bids
    else:
        bids_tuple = tuple(updated_counter_levels)
        asks_tuple = book.asks

    resting_order: Order | None = None
    cancelled_qty = 0

    # If incoming order has remaining quantity:
    if rem_taker_qty > 0:
        if is_market:
            # Market orders do not rest on the book; remainder is cancelled
            cancelled_qty = rem_taker_qty
        else:
            # Limit order rests on the book
            resting_order = replace(incoming, remaining_qty=rem_taker_qty)
            new_index[resting_order.order_id] = (taker_side, resting_order.price)

            if taker_side == Side.BUY:
                bids_tuple = _insert_resting_order(bids_tuple, resting_order, descending=True)
            else:
                asks_tuple = _insert_resting_order(asks_tuple, resting_order, descending=False)

    new_book = OrderBook(
        bids=bids_tuple,
        asks=asks_tuple,
        order_index=new_index,
    )

    return MatchResult(
        book=new_book,
        trades=tuple(trades),
        resting_order=resting_order,
        cancelled_quantity=cancelled_qty,
    )


def _insert_resting_order(
    levels: Sequence[PriceLevel],
    order: Order,
    descending: bool,
) -> tuple[PriceLevel, ...]:
    """Insert a resting order into sorted price levels tuple."""
    res_levels = list(levels)
    inserted = False

    for i, level in enumerate(res_levels):
        if level.price == order.price:
            res_levels[i] = level.add_order(order)
            inserted = True
            break
        elif (descending and level.price < order.price) or (not descending and level.price > order.price):
            new_level = PriceLevel(price=order.price, orders=(order,))
            res_levels.insert(i, new_level)
            inserted = True
            break

    if not inserted:
        res_levels.append(PriceLevel(price=order.price, orders=(order,)))

    return tuple(res_levels)
