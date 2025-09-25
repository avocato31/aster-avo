from __future__ import annotations

import math
import os
import time
import uuid
from dataclasses import dataclass
from typing import Optional, Dict, Any

import requests
from eth_abi import encode
from eth_account import Account
from eth_account.messages import encode_defunct
from web3 import Web3

from .base import ExchangeClient, OrderResult, Side, PositionSide


@dataclass
class AsterAuth:
    user: str
    signer: str
    private_key: str


class AsterFuturesV3Client(ExchangeClient):
    def __init__(self, base_url: str, auth: AsterAuth, recv_window: int = 50000, send_order_in_query: bool = True):
        self.base_url = base_url.rstrip("/")
        self.auth = auth
        self.recv_window = recv_window
        self.send_order_in_query = send_order_in_query
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "hedge-aster-bot/1.0"})
        self._symbol_info_cache: Dict[str, Dict[str, Any]] = {}

    def _nonce(self) -> int:
        return math.trunc(time.time() * 1000000)

    def _timestamp_ms(self) -> int:
        return int(round(time.time() * 1000))

    def _sign(self, params: dict) -> dict:
        filtered = {k: v for k, v in params.items() if v is not None}
        filtered["recvWindow"] = str(self.recv_window)
        filtered["timestamp"] = str(self._timestamp_ms())
        # normalize all values to string and stable json
        def _normalize(d: dict) -> dict:
            nd = {}
            for k, v in d.items():
                if isinstance(v, (list, tuple)):
                    nd[k] = str([str(i) if not isinstance(i, dict) else str(_normalize(i)) for i in v])
                elif isinstance(v, dict):
                    nd[k] = str(_normalize(v))
                else:
                    nd[k] = str(v)
            return nd
        norm = _normalize(filtered)
        import json
        json_str = json.dumps(norm, sort_keys=True).replace(" ", "").replace("'", '"')
        nonce = self._nonce()
        encoded = encode(['string', 'address', 'address', 'uint256'], [json_str, self.auth.user, self.auth.signer, nonce])
        keccak_hex = Web3.keccak(encoded).hex()
        signable_msg = encode_defunct(hexstr=keccak_hex)
        signed = Account.sign_message(signable_message=signable_msg, private_key=self.auth.private_key)
        norm['nonce'] = str(nonce)
        norm['user'] = self.auth.user
        norm['signer'] = self.auth.signer
        norm['signature'] = '0x' + signed.signature.hex()
        return norm

    def _request(self, method: str, path: str, params: dict) -> dict:
        if path == '/fapi/v3/order':
            print('[debug] unsigned params:', params)
        body = self._sign(params)
        if path == '/fapi/v3/order':
            print('[debug] signed body:', {k: (body[k] if k not in ('signature', 'privateKey') else '***') for k in body})
        url = f"{self.base_url}{path}"
        if method == 'POST':
            if self.send_order_in_query and path == '/fapi/v3/order':
                resp = self.session.post(url, params=body)
            else:
                resp = self.session.post(url, data=body)
        elif method == 'GET':
            resp = self.session.get(url, params=body)
        elif method == 'DELETE':
            resp = self.session.delete(url, data=body)
        else:
            raise ValueError("unsupported method")
        if resp.status_code >= 400:
            print(f"HTTP {resp.status_code} error body: {resp.text}")
            resp.raise_for_status()
        return resp.json() if resp.text else {}

    def set_margin_type(self, symbol: str, margin_type: str = 'CROSSED') -> None:
        self._request('POST', '/fapi/v1/marginType', {'symbol': symbol, 'marginType': margin_type})

    def set_leverage(self, symbol: str, leverage: int = 10) -> None:
        self._request('POST', '/fapi/v1/leverage', {'symbol': symbol, 'leverage': leverage})

    def _get_symbol_filters(self, symbol: str) -> Dict[str, Any]:
        if symbol in self._symbol_info_cache:
            return self._symbol_info_cache[symbol]
        try:
            data = self._request('GET', '/fapi/v1/exchangeInfo', {})
        except Exception:
            data = {}
        filters_map = {}
        if isinstance(data, dict) and 'symbols' in data:
            for s in data['symbols']:
                if s.get('symbol') == symbol:
                    for f in s.get('filters', []):
                        filters_map[f.get('filterType')] = f
                    break
        self._symbol_info_cache[symbol] = filters_map
        return filters_map

    def _round_qty(self, symbol: str, qty: float) -> float:
        filters = self._get_symbol_filters(symbol)
        mls = filters.get('MARKET_LOT_SIZE') or filters.get('LOT_SIZE') or {}
        step = float(mls.get('stepSize', '0.00000001')) if mls else 0.00000001
        min_qty = float(mls.get('minQty', '0')) if mls else 0.0
        if step <= 0:
            step = 0.00000001
        rounded = math.floor(qty / step) * step
        if rounded < min_qty:
            rounded = min_qty
        return float(f"{rounded:.18f}")

    async def create_market_order(self, symbol: str, side: Side, quote_amount_usd: float, position_side: PositionSide = "BOTH") -> OrderResult:
        try:
            self.set_margin_type(symbol, 'CROSSED')
            self.set_leverage(symbol, 10)
        except Exception as e:
            print(f"Config warn: {e}")
        price = await self.get_price(symbol)
        qty = quote_amount_usd / price if price else 0
        qty = self._round_qty(symbol, qty)
        params = {
            'symbol': symbol,
            'type': 'MARKET',
            'side': 'BUY' if side == 'buy' else 'SELL',
            'quantity': f"{qty}",
            'positionSide': 'BOTH',
            'newClientOrderId': f"hast-{uuid.uuid4().hex[:12]}",
        }
        data = self._request('POST', '/fapi/v3/order', params)
        executed_qty = float(data.get('executedQty', data.get('cumQty', 0) or 0))
        avg_price = float(data.get('avgPrice', 0) or 0)
        return OrderResult(order_id=str(data.get('orderId', '')), symbol=symbol, side=side, executed_qty=executed_qty, avg_price=avg_price)

    async def close_position_market(self, symbol: str, side: Side, qty: float, position_side: PositionSide = "BOTH") -> Optional[OrderResult]:
        qty = self._round_qty(symbol, qty)
        params = {
            'symbol': symbol,
            'type': 'MARKET',
            'side': 'SELL' if side == 'buy' else 'BUY',
            'reduceOnly': True,
            'quantity': f"{qty}",
            'positionSide': 'BOTH',
            'newClientOrderId': f"hast-close-{uuid.uuid4().hex[:12]}",
        }
        data = self._request('POST', '/fapi/v3/order', params)
        executed_qty = float(data.get('executedQty', data.get('cumQty', 0) or 0))
        avg_price = float(data.get('avgPrice', 0) or 0)
        return OrderResult(order_id=str(data.get('orderId', '')), symbol=symbol, side='sell' if side=='buy' else 'buy', executed_qty=executed_qty, avg_price=avg_price)

    async def get_price(self, symbol: str) -> float:
        data = self._request('GET', '/fapi/v1/ticker/price', {'symbol': symbol})
        return float(data.get('price', 0))

    async def get_position(self, symbol: str) -> Optional[dict]:
        try:
            data = self._request('GET', '/fapi/v3/positionRisk', {'symbol': symbol})
            if isinstance(data, list) and data:
                return data[0]
            return data
        except Exception:
            return None
