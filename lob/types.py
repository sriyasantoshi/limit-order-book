from enum import Enum
from typing import NewType, TypeAlias

class Side(str, Enum):
    """Side of the order book: BUY or SELL."""
    BUY = "BUY"
    SELL = "SELL"

    def opposite(self) -> "Side":
        return Side.SELL if self == Side.BUY else Side.BUY


class OrderType(str, Enum):
    """Type of order event."""
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    CANCEL = "CANCEL"


Price: TypeAlias = int      # Price in integer ticks (e.g. 10050 = $100.50)
Quantity: TypeAlias = int   # Order quantity in integer units
OrderId: TypeAlias = str    # Unique order identifier
Timestamp: TypeAlias = int  # Monotonic nanosecond timestamp or sequence number
