import pytest
from lob.types import Side, OrderType
from lob.model import Order, MatchResult, CancelResult
from lob.engine import empty_book, process_order


def test_empty_book() -> None:
    book = empty_book()
    assert book.best_bid is None
    assert book.best_ask is None
    assert book.spread is None
    assert not book.is_crossed
    assert book.total_bid_volume == 0
    assert book.total_ask_volume == 0


def test_single_limit_buy() -> None:
    book = empty_book()
    order = Order(
        order_id="O1",
        side=Side.BUY,
        price=10000,
        quantity=10,
        remaining_qty=10,
        timestamp=1,
    )
    res = process_order(book, order)
    assert isinstance(res, MatchResult)
    assert len(res.trades) == 0
    assert res.book.best_bid == 10000
    assert res.book.best_ask is None
    assert res.book.total_bid_volume == 10


def test_limit_buy_and_sell_matching() -> None:
    book = empty_book()

    # Place resting SELL limit order at 100.00
    sell_order = Order(
        order_id="S1",
        side=Side.SELL,
        price=10000,
        quantity=10,
        remaining_qty=10,
        timestamp=1,
    )
    res1 = process_order(book, sell_order)
    book1 = res1.book
    assert book1.best_ask == 10000

    # Incoming BUY limit order at 100.00 -> exact match
    buy_order = Order(
        order_id="B1",
        side=Side.BUY,
        price=10000,
        quantity=10,
        remaining_qty=10,
        timestamp=2,
    )
    res2 = process_order(book1, buy_order)
    assert isinstance(res2, MatchResult)
    assert len(res2.trades) == 1

    trade = res2.trades[0]
    assert trade.maker_order_id == "S1"
    assert trade.taker_order_id == "B1"
    assert trade.price == 10000
    assert trade.quantity == 10

    # Book should be empty after exact match
    assert res2.book.best_bid is None
    assert res2.book.best_ask is None


def test_partial_fill() -> None:
    book = empty_book()

    # Resting SELL for 10 units at 105.00
    sell_order = Order(
        order_id="S1",
        side=Side.SELL,
        price=10500,
        quantity=10,
        remaining_qty=10,
        timestamp=1,
    )
    book = process_order(book, sell_order).book

    # Incoming BUY for 4 units at 105.00
    buy_order = Order(
        order_id="B1",
        side=Side.BUY,
        price=10500,
        quantity=4,
        remaining_qty=4,
        timestamp=2,
    )
    res = process_order(book, buy_order)
    assert isinstance(res, MatchResult)
    assert len(res.trades) == 1
    assert res.trades[0].quantity == 4

    # 6 units should remain on ask side
    assert res.book.best_ask == 10500
    assert res.book.total_ask_volume == 6


def test_market_order_filling_multiple_levels() -> None:
    book = empty_book()

    # Place asks at 100.00 (5 units) and 101.00 (10 units)
    s1 = Order("S1", Side.SELL, 10000, 5, 5, 1)
    s2 = Order("S2", Side.SELL, 10100, 10, 10, 2)
    book = process_order(book, s1).book
    book = process_order(book, s2).book

    # Market BUY for 12 units
    m_buy = Order("M1", Side.BUY, 0, 12, 12, 3, order_type=OrderType.MARKET)
    res = process_order(book, m_buy)
    assert isinstance(res, MatchResult)
    assert len(res.trades) == 2

    # First trade: 5 units at 100.00
    assert res.trades[0].maker_order_id == "S1"
    assert res.trades[0].price == 10000
    assert res.trades[0].quantity == 5

    # Second trade: 7 units at 101.00
    assert res.trades[1].maker_order_id == "S2"
    assert res.trades[1].price == 10100
    assert res.trades[1].quantity == 7

    # Remaining on ask side: 3 units at 101.00
    assert res.book.best_ask == 10100
    assert res.book.total_ask_volume == 3


def test_cancel_order() -> None:
    book = empty_book()
    b1 = Order("B1", Side.BUY, 9900, 10, 10, 1)
    book = process_order(book, b1).book
    assert book.best_bid == 9900

    # Cancel B1
    c1 = Order("B1", Side.BUY, 0, 0, 0, 2, order_type=OrderType.CANCEL)
    res = process_order(book, c1)
    assert isinstance(res, CancelResult)
    assert res.success
    assert res.cancelled_order is not None
    assert res.cancelled_order.order_id == "B1"
    assert res.book.best_bid is None


def test_price_time_priority() -> None:
    book = empty_book()

    # Two orders at price 100.00
    s1 = Order("S1", Side.SELL, 10000, 5, 5, 1)
    s2 = Order("S2", Side.SELL, 10000, 5, 5, 2)
    book = process_order(book, s1).book
    book = process_order(book, s2).book

    # Buy order for 6 units -> fills all of S1 (5 units) and 1 unit of S2
    b1 = Order("B1", Side.BUY, 10000, 6, 6, 3)
    res = process_order(book, b1)
    assert isinstance(res, MatchResult)
    assert len(res.trades) == 2
    assert res.trades[0].maker_order_id == "S1"
    assert res.trades[0].quantity == 5
    assert res.trades[1].maker_order_id == "S2"
    assert res.trades[1].quantity == 1
