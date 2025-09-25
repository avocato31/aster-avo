from __future__ import annotations

import asyncio
import random
from typing import Optional

from .base import ExchangeClient, OrderResult, Side


class StubExchangeClient(ExchangeClient):
    def __init__(self, name: str):
        self.name = name

    async def create_market_order(self, symbol: str, side: Side, quote_amount_usd: float) -> OrderResult:
        await asyncio.sleep(0.2)
        price = await self.get_price(symbol)
        executed_qty = quote_amount_usd / price
        return OrderResult(
            order_id=f"{self.name}-{random.randint(100000, 999999)}",
            symbol=symbol,
            side=side,
            executed_qty=executed_qty,
            avg_price=price,
        )

    async def close_position_market(self, symbol: str, side: Side, qty: float) -> Optional[OrderResult]:
        await asyncio.sleep(0.1)
        price = await self.get_price(symbol)
        return OrderResult(
            order_id=f"{self.name}-close-{random.randint(100000, 999999)}",
            symbol=symbol,
            side="sell" if side == "buy" else "buy",
            executed_qty=qty,
            avg_price=price,
        )

    async def get_price(self, symbol: str) -> float:
        base_prices = {
            "BTCUSDT": 60000.0,
            "ETHUSDT": 2500.0,
            "SOLUSDT": 150.0,
            "BNBUSDT": 550.0,
            "XRPUSDT": 0.6,
        }
        jitter = 1 + random.uniform(-0.002, 0.002)
        return base_prices.get(symbol, 100.0) * jitter

    async def get_position(self, symbol: str) -> Optional[dict]:
        return None
