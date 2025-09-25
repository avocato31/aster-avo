from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Literal


Side = Literal["buy", "sell"]
PositionSide = Literal["LONG", "SHORT", "BOTH"]


@dataclass
class OrderResult:
    order_id: str
    symbol: str
    side: Side
    executed_qty: float
    avg_price: float


class ExchangeClient:
    async def create_market_order(self, symbol: str, side: Side, quote_amount_usd: float, position_side: PositionSide = "BOTH") -> OrderResult:
        raise NotImplementedError

    async def close_position_market(self, symbol: str, side: Side, qty: float, position_side: PositionSide = "BOTH") -> Optional[OrderResult]:
        raise NotImplementedError

    async def get_price(self, symbol: str) -> float:
        raise NotImplementedError

    async def get_position(self, symbol: str) -> Optional[dict]:
        raise NotImplementedError
