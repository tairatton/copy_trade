"""
Data models for Copy Trade system.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class OrderDirection(Enum):
    """Trade direction."""
    BUY = 0
    SELL = 1


class TradeEventType(Enum):
    """Types of trade events detected by the monitor."""
    NEW_POSITION = "NEW"
    CLOSED_POSITION = "CLOSED"
    MODIFIED_SL = "MODIFIED_SL"
    MODIFIED_TP = "MODIFIED_TP"
    PARTIAL_CLOSE = "PARTIAL_CLOSE"


@dataclass
class TradePosition:
    """Represents an open position from MT5."""
    ticket: int
    symbol: str
    type: int               # 0 = BUY, 1 = SELL
    volume: float
    price_open: float
    price_current: float
    sl: float
    tp: float
    profit: float
    swap: float
    time: datetime
    time_update: datetime
    magic: int
    comment: str

    @property
    def direction(self) -> str:
        return "BUY" if self.type == 0 else "SELL"

    @property
    def sl_distance_points(self) -> Optional[float]:
        """SL distance from open price in price units (not points)."""
        if self.sl == 0.0:
            return None
        return abs(self.price_open - self.sl)


@dataclass
class TradeEvent:
    """An event detected by monitoring master account."""
    event_type: TradeEventType
    master_ticket: int
    position: Optional[TradePosition] = None
    previous_position: Optional[TradePosition] = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class OrderResult:
    """Result of an order operation."""
    success: bool
    ticket: Optional[int] = None
    volume: Optional[float] = None
    price: Optional[float] = None
    error_code: Optional[int] = None
    error_message: Optional[str] = None
    retcode: Optional[int] = None


@dataclass
class PositionMapping:
    """Mapping between master and slave positions."""
    master_ticket: int
    slave_ticket: int
    symbol: str
    direction: str
    master_volume: float
    slave_volume: float
    master_open_price: float
    slave_open_price: float
    master_sl: float = 0.0
    master_tp: float = 0.0
    slave_sl: float = 0.0
    slave_tp: float = 0.0
    opened_at: str = ""
    risk_percent: float = 0.0

    def to_dict(self) -> dict:
        return {
            "master_ticket": self.master_ticket,
            "slave_ticket": self.slave_ticket,
            "symbol": self.symbol,
            "direction": self.direction,
            "master_volume": self.master_volume,
            "slave_volume": self.slave_volume,
            "master_open_price": self.master_open_price,
            "slave_open_price": self.slave_open_price,
            "master_sl": self.master_sl,
            "master_tp": self.master_tp,
            "slave_sl": self.slave_sl,
            "slave_tp": self.slave_tp,
            "opened_at": self.opened_at,
            "risk_percent": self.risk_percent,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PositionMapping":
        return cls(**data)
