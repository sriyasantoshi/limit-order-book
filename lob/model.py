from dataclasses import dataclass, replace, field
from typing import Self
from lob.types import Side, OrderType, Price, Quantity, OrderId, Timestamp

@dataclass(frozen=True, slots=True)
class Order:
    """Immutable order representation."""
    order_id: OrderId
    side: Side
    price: Price
    quantity: Quantity
    remaining_qty: Quantity
    timestamp: Timestamp
    order_type: OrderType = OrderType.LIMIT

    def with_filled(self, filled_qty: Quantity) -> Self:
        """Return a new order with remaining_qty reduced by filled_qty."""
        if filled_qty > self.remaining_qty:
            raise ValueError(
                f"Cannot fill {filled_qty} units on order {self.order_id} "
                f"with remaining_qty {self.remaining_qty}"
            )
        return replace(self, remaining_qty=self.remaining_qty - filled_qty)


@dataclass(frozen=True, slots=True)
class Trade:
    """Immutable trade execution record."""
    trade_id: str
    maker_order_id: OrderId
    taker_order_id: OrderId
    price: Price
    quantity: Quantity
    taker_side: Side
    timestamp: Timestamp


@dataclass(frozen=True, slots=True)
class PriceLevel:
    """Immutable price level containing a FIFO queue of orders at a specific price."""
    price: Price
    orders: tuple[Order, ...]

    @property
    def total_volume(self) -> Quantity:
        return sum(o.remaining_qty for o in self.orders)

    def add_order(self, order: Order) -> Self:
        return replace(self, orders=(*self.orders, order))

    def remove_order(self, order_id: OrderId) -> Self:
        new_orders = tuple(o for o in self.orders if o.order_id != order_id)
        return replace(self, orders=new_orders)


@dataclass(frozen=True, slots=True)
class OrderBook:
    """
    Immutable Limit Order Book.
    
    bids: Sorted by price DESCENDING (highest bid first).
    asks: Sorted by price ASCENDING (lowest ask first).
    order_index: Fast mapping from order_id -> (side, price).
    """
    bids: tuple[PriceLevel, ...] = ()
    asks: tuple[PriceLevel, ...] = ()
    order_index: dict[OrderId, tuple[Side, Price]] = field(default_factory=dict)

    @property
    def best_bid(self) -> Price | None:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Price | None:
        return self.asks[0].price if self.asks else None

    @property
    def spread(self) -> Price | None:
        bb, ba = self.best_bid, self.best_ask
        if bb is not None and ba is not None:
            return ba - bb
        return None

    @property
    def is_crossed(self) -> bool:
        bb, ba = self.best_bid, self.best_ask
        if bb is not None and ba is not None:
            return bb >= ba
        return False

    @property
    def total_bid_volume(self) -> Quantity:
        return sum(level.total_volume for level in self.bids)

    @property
    def total_ask_volume(self) -> Quantity:
        return sum(level.total_volume for level in self.asks)

    def get_order(self, order_id: OrderId) -> Order | None:
        loc = self.order_index.get(order_id)
        if loc is None:
            return None
        side, price = loc
        levels = self.bids if side == Side.BUY else self.asks
        for level in levels:
            if level.price == price:
                for order in level.orders:
                    if order.order_id == order_id:
                        return order
        return None


@dataclass(frozen=True, slots=True)
class MatchResult:
    """Result of processing a Limit or Market order against the book."""
    book: OrderBook
    trades: tuple[Trade, ...]
    resting_order: Order | None
    cancelled_quantity: Quantity = 0


@dataclass(frozen=True, slots=True)
class CancelResult:
    """Result of attempting to cancel an order from the book."""
    book: OrderBook
    cancelled_order: Order | None
    success: bool
