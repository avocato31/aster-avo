from __future__ import annotations

import hashlib
import hmac
import math
import time
import urllib.parse
from typing import Dict, Any, Optional

import requests

from .base import ExchangeClient, OrderResult, Side


class AsterV1HmacClient(ExchangeClient):
    def __init__(self, base_url: str, api_key: str, api_secret: str, recv_window_ms: int = 5000):
        self.base = base_url.rstrip('/')
        self.api_key = api_key
        self.api_secret = api_secret.encode()
        self.recv_window = recv_window_ms
        self.session = requests.Session()
        if self.api_key:
            self.session.headers.update({'X-MBX-APIKEY': self.api_key, 'Content-Type': 'application/x-www-form-urlencoded'})
        self._symbol_info_cache: Dict[str, Dict[str, Any]] = {}

    def _ts(self) -> int:
        return int(time.time() * 1000)

    def _sign_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        # Aster (Binance tarzı) HMAC: imza, gönderilen sorgu dizesinin birebir aynı
        # anahtar-değer sırası ile hesaplanmalı. Bu nedenle sıralama yapılmaz.
        params = {k: v for k, v in params.items() if v is not None}
        params.update({'timestamp': str(self._ts()), 'recvWindow': str(self.recv_window)})
        query = urllib.parse.urlencode(params, doseq=True)
        sig = hmac.new(self.api_secret, query.encode(), hashlib.sha256).hexdigest()
        params['signature'] = sig
        return params

    def _post(self, path: str, params: Dict[str, Any]) -> Dict[str, Any]:
        signed = self._sign_params(params)
        url = self.base + path
        r = self.session.post(url, data=signed, timeout=15)
        if r.status_code >= 400:
            print(f"[hmac v1] POST {url} -> HTTP {r.status_code}: {r.text}")
        r.raise_for_status()
        return r.json() if r.text else {}

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None, signed: bool = False) -> Dict[str, Any]:
        params = params or {}
        if signed:
            params = self._sign_params(params)
        url = self.base + path
        r = self.session.get(url, params=params, timeout=15)
        if r.status_code >= 400:
            print(f"[hmac v1] GET {url} -> HTTP {r.status_code}: {r.text}")
        r.raise_for_status()
        return r.json()

    def _get_symbol_filters(self, symbol: str) -> Dict[str, Any]:
        if symbol in self._symbol_info_cache:
            return self._symbol_info_cache[symbol]
        try:
            data = self._get('/fapi/v1/exchangeInfo', {})
        except Exception:
            data = {}
        filters_map: Dict[str, Any] = {}
        if isinstance(data, dict) and 'symbols' in data:
            for s in data['symbols']:
                if s.get('symbol') == symbol:
                    for f in s.get('filters', []):
                        filters_map[f.get('filterType')] = f
                    break
        self._symbol_info_cache[symbol] = filters_map
        return filters_map

    def _round_qty(self, symbol: str, qty: float) -> float:
        try:
            filters = self._get_symbol_filters(symbol)
            mls = filters.get('MARKET_LOT_SIZE') or filters.get('LOT_SIZE') or {}
            step_str = mls.get('stepSize', '0.00000001')
            min_qty = float(mls.get('minQty', '0')) if mls else 0.0
        except Exception:
            step_str = '0.00000001'
            min_qty = 0.0
        from decimal import Decimal, ROUND_DOWN, getcontext
        getcontext().prec = 28
        step_dec = Decimal(step_str)
        qty_dec = Decimal(str(qty))
        if step_dec <= 0:
            step_dec = Decimal('0.00000001')
        rounded = qty_dec.quantize(step_dec, rounding=ROUND_DOWN)
        if rounded < Decimal(str(min_qty)):
            rounded = Decimal(str(min_qty))
        return float(rounded)

    def _format_qty(self, symbol: str, qty: float) -> str:
        # Format with the exact number of decimals implied by stepSize, avoiding extra precision
        try:
            filters = self._get_symbol_filters(symbol)
            mls = filters.get('MARKET_LOT_SIZE') or filters.get('LOT_SIZE') or {}
            step_str = mls.get('stepSize', '0.00000001')
        except Exception:
            step_str = '0.00000001'
        from decimal import Decimal, ROUND_DOWN, getcontext
        getcontext().prec = 28
        step_dec = Decimal(step_str)
        qty_dec = Decimal(str(qty)).quantize(step_dec, rounding=ROUND_DOWN)
        # Normalize to string without scientific notation
        s = format(qty_dec, 'f')
        if '.' in s:
            s = s.rstrip('0').rstrip('.') if step_dec.as_tuple().exponent == 0 else s.rstrip('0').rstrip('.')
        return s

    async def get_price(self, symbol: str) -> float:
        data = self._get('/fapi/v1/ticker/price', {'symbol': symbol})
        return float(data.get('price', 0))

    async def create_market_order(self, symbol: str, side: Side, quote_amount_usd: float) -> OrderResult:
        # Futures için miktarı hesaplayıp quantity göndermek daha uyumlu
        price = await self.get_price(symbol)
        qty = max(quote_amount_usd / price, 0)
        qty = self._round_qty(symbol, qty)
        import uuid as _uuid
        params: Dict[str, Any] = {
            'symbol': symbol,
            'type': 'MARKET',
            'side': 'BUY' if side == 'buy' else 'SELL',
            'quantity': self._format_qty(symbol, qty),
            'positionSide': 'BOTH',
            'newClientOrderId': f"hmac-{_uuid.uuid4().hex[:12]}",
        }
        data = self._post('/fapi/v1/order', params)
        executed_qty = float(data.get('executedQty', data.get('cumQty', 0) or 0))
        avg_price = float(data.get('avgPrice', 0) or 0)
        return OrderResult(order_id=str(data.get('orderId', '')), symbol=symbol, side=side, executed_qty=executed_qty, avg_price=avg_price)

    async def close_position_market(self, symbol: str, side: Side, qty: float) -> Optional[OrderResult]:
        qty = self._round_qty(symbol, qty)
        import uuid as _uuid
        params: Dict[str, Any] = {
            'symbol': symbol,
            'type': 'MARKET',
            'side': 'SELL' if side == 'buy' else 'BUY',
            'quantity': self._format_qty(symbol, qty),
            'positionSide': 'BOTH',
            'reduceOnly': 'true',
            'newClientOrderId': f"hmac-close-{_uuid.uuid4().hex[:12]}",
        }
        data = self._post('/fapi/v1/order', params)
        executed_qty = float(data.get('executedQty', data.get('cumQty', 0) or 0))
        avg_price = float(data.get('avgPrice', 0) or 0)
        return OrderResult(order_id=str(data.get('orderId', '')), symbol=symbol, side='sell' if side=='buy' else 'buy', executed_qty=executed_qty, avg_price=avg_price)

    async def get_position(self, symbol: str) -> Optional[dict]:
        # Retry with backoff, then fallback to account if needed
        delays = [0.3, 0.6, 1.2]
        last_err: Optional[Exception] = None
        for d in delays:
            try:
                data = self._get('/fapi/v2/positionRisk', {'symbol': symbol}, signed=True)
                if isinstance(data, list):
                    return data[0] if data else None
                return data
            except Exception as e:
                last_err = e
                time.sleep(d)
        try:
            acc = self._get('/fapi/v1/account', {}, signed=True)
            # Derive symbol exposure if available
            if isinstance(acc, dict) and 'positions' in acc:
                for p in acc.get('positions', []):
                    if p.get('symbol') == symbol:
                        return p
        except Exception:
            pass
        if last_err:
            print(f"[position] fallback failed: {last_err}")
        return None
