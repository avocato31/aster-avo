from __future__ import annotations

import os
import asyncio
import random
import uuid
from datetime import datetime, timedelta, UTC

from src.api.stub_client import StubExchangeClient
from src.reporting import Reporter, TradeRecord
from src.config import Settings

try:
    from src.api.aster_futures_v3 import AsterFuturesV3Client, AsterAuth
except Exception:
    AsterFuturesV3Client = None  # type: ignore
    AsterAuth = None  # type: ignore

try:
    from src.api.aster_v1_hmac import AsterV1HmacClient
except Exception:
    AsterV1HmacClient = None  # type: ignore


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def run_cycle(settings: Settings, reporter: Reporter, a_client, b_client) -> None:
    cycle_id = uuid.uuid4().hex[:8]
    symbol = random.choice(settings.symbols)
    quote_usd = round(random.uniform(settings.min_usd, settings.max_usd), 2)

    first_is_long = random.choice([True, False])
    a_side = "buy" if first_is_long else "sell"
    b_side = "sell" if first_is_long else "buy"

    # Open A with simple retry
    for attempt in range(3):
        try:
            a_open = await a_client.create_market_order(symbol=symbol, side=a_side, quote_amount_usd=quote_usd)
            break
        except Exception as e:
            if attempt == 2:
                raise
            await asyncio.sleep(0.5 * (attempt + 1))
    reporter.write_trade(
        TradeRecord(
            timestamp=_now_iso(),
            cycle_id=cycle_id,
            symbol=symbol,
            account="A",
            side=a_side,
            action="open",
            quote_usd=quote_usd,
            executed_qty=a_open.executed_qty,
            avg_price=a_open.avg_price,
        )
    )

    # Open B with simple retry
    for attempt in range(3):
        try:
            b_open = await b_client.create_market_order(symbol=symbol, side=b_side, quote_amount_usd=quote_usd)
            break
        except Exception as e:
            if attempt == 2:
                raise
            await asyncio.sleep(0.5 * (attempt + 1))
    reporter.write_trade(
        TradeRecord(
            timestamp=_now_iso(),
            cycle_id=cycle_id,
            symbol=symbol,
            account="B",
            side=b_side,
            action="open",
            quote_usd=quote_usd,
            executed_qty=b_open.executed_qty,
            avg_price=b_open.avg_price,
        )
    )

    hold_minutes = random.randint(settings.hold_min_minutes, settings.hold_max_minutes)
    await asyncio.sleep(hold_minutes * 60)

    # Refresh actual positions from exchange
    a_pos = await a_client.get_position(symbol)
    b_pos = await b_client.get_position(symbol)
    a_qty = float(a_pos.get('positionAmt', a_open.executed_qty) or 0) if isinstance(a_pos, dict) else a_open.executed_qty
    b_qty = float(b_pos.get('positionAmt', b_open.executed_qty) or 0) if isinstance(b_pos, dict) else b_open.executed_qty
    a_qty = abs(a_qty)
    b_qty = abs(b_qty)

    # Close A
    print(f"[close] A closing {symbol} side={a_side} qty={a_qty}")
    await asyncio.sleep(0.2)
    if a_qty > 0:
        for attempt in range(3):
            try:
                await a_client.close_position_market(symbol, a_side, a_qty)
                break
            except Exception:
                if attempt == 2:
                    raise
                await asyncio.sleep(0.5 * (attempt + 1))
        # Post-close verify and double-shot if needed
        await asyncio.sleep(0.3)
        a_pos2 = await a_client.get_position(symbol)
        rem_a = float(a_pos2.get('positionAmt', 0) or 0) if isinstance(a_pos2, dict) else 0.0
        rem_a = abs(rem_a)
        if rem_a > 0:
            print(f"[close] A residual {rem_a} detected, sending second reduceOnly close")
            for attempt in range(3):
                try:
                    await a_client.close_position_market(symbol, a_side, rem_a)
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(0.5 * (attempt + 1))
    reporter.write_trade(
        TradeRecord(
            timestamp=_now_iso(),
            cycle_id=cycle_id,
            symbol=symbol,
            account="A",
            side=a_side,
            action="close",
            quote_usd=0.0,
            executed_qty=a_open.executed_qty,
            avg_price=0.0,
        )
    )

    # Close B
    print(f"[close] B closing {symbol} side={b_side} qty={b_qty}")
    await asyncio.sleep(0.2)
    if b_qty > 0:
        for attempt in range(3):
            try:
                await b_client.close_position_market(symbol, b_side, b_qty)
                break
            except Exception:
                if attempt == 2:
                    raise
                await asyncio.sleep(0.5 * (attempt + 1))
        # Post-close verify and double-shot if needed
        await asyncio.sleep(0.3)
        b_pos2 = await b_client.get_position(symbol)
        rem_b = float(b_pos2.get('positionAmt', 0) or 0) if isinstance(b_pos2, dict) else 0.0
        rem_b = abs(rem_b)
        if rem_b > 0:
            print(f"[close] B residual {rem_b} detected, sending second reduceOnly close")
            for attempt in range(3):
                try:
                    await b_client.close_position_market(symbol, b_side, rem_b)
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    await asyncio.sleep(0.5 * (attempt + 1))
    reporter.write_trade(
        TradeRecord(
            timestamp=_now_iso(),
            cycle_id=cycle_id,
            symbol=symbol,
            account="B",
            side=b_side,
            action="close",
            quote_usd=0.0,
            executed_qty=b_open.executed_qty,
            avg_price=0.0,
        )
    )


async def main() -> None:
    settings = Settings.load()
    reporter = Reporter(report_dir=settings.report_dir, tz_name=settings.tz)

    a_client = None
    b_client = None

    # Prefer stub if forced explicitly
    selected_mode = ""
    if os.getenv("FORCE_STUB", "0") not in ("", "0", "false", "False"):
        print("[mode] FORCE_STUB=1 → using STUB client")
        a_client = StubExchangeClient("accountA")
        b_client = StubExchangeClient("accountB")
        selected_mode = "STUB"
    # Prefer HMAC v1 if keys exist
    elif AsterV1HmacClient and settings.hmac_api_key_a and settings.hmac_api_secret_a and settings.hmac_api_key_b and settings.hmac_api_secret_b:
        print("[mode] Using Aster HMAC v1 client for both accounts (mainnet)")
        a_client = AsterV1HmacClient(settings.fapi_base_url, settings.hmac_api_key_a, settings.hmac_api_secret_a)
        b_client = AsterV1HmacClient(settings.fapi_base_url, settings.hmac_api_key_b, settings.hmac_api_secret_b)
        selected_mode = "HMAC"
    # Else try EVM v3
    elif AsterFuturesV3Client and settings.aster_user_a and settings.aster_private_key_a and settings.aster_user_b and settings.aster_private_key_b:
        print("[mode] Using Aster Futures v3 EVM-signed client (mainnet)")
        auth_a = AsterAuth(user=settings.aster_user_a, signer=settings.aster_signer_a or settings.aster_user_a, private_key=settings.aster_private_key_a)
        auth_b = AsterAuth(user=settings.aster_user_b, signer=settings.aster_signer_b or settings.aster_user_b, private_key=settings.aster_private_key_b)
        a_client = AsterFuturesV3Client(settings.fapi_base_url, auth_a, recv_window=50000, send_order_in_query=True)
        b_client = AsterFuturesV3Client(settings.fapi_base_url, auth_b, recv_window=50000, send_order_in_query=True)
        selected_mode = "V3"
    else:
        print("[mode] Using STUB client (development/demo only)")
        a_client = StubExchangeClient("accountA")
        b_client = StubExchangeClient("accountB")
        selected_mode = "STUB"

    # Preflight: if HMAC selected but signature invalid, downgrade to V3 if creds available
    if selected_mode == "HMAC":
        try:
            # signed endpoint with minimal risk
            await a_client.get_position(settings.symbols[0])
        except Exception as e:
            msg = str(e)
            if ("Signature" in msg or "-1022" in msg or "-1102" in msg or "HTTP" in msg) and AsterFuturesV3Client and settings.aster_user_a and settings.aster_private_key_a and settings.aster_user_b and settings.aster_private_key_b:
                print("[mode] HMAC signature invalid, falling back to V3 EVM client")
                auth_a = AsterAuth(user=settings.aster_user_a, signer=settings.aster_signer_a or settings.aster_user_a, private_key=settings.aster_private_key_a)
                auth_b = AsterAuth(user=settings.aster_user_b, signer=settings.aster_signer_b or settings.aster_user_b, private_key=settings.aster_private_key_b)
                a_client = AsterFuturesV3Client(settings.fapi_base_url, auth_a, recv_window=50000, send_order_in_query=True)
                b_client = AsterFuturesV3Client(settings.fapi_base_url, auth_b, recv_window=50000, send_order_in_query=True)
                selected_mode = "V3"

    run_once = os.getenv("RUN_ONCE", "0") not in ("", "0", "false", "False")
    max_runtime_minutes_env = os.getenv("RUN_MAX_MINUTES", "")
    max_runtime: float | None = float(max_runtime_minutes_env) if max_runtime_minutes_env.strip() else None
    start_time = datetime.now(UTC)

    while True:
        # If RUN_ONCE enabled, make this cycle instantaneous (no hold/cooldown) by overriding ranges
        if run_once:
            original_hold_min = settings.hold_min_minutes
            original_hold_max = settings.hold_max_minutes
            original_cooldown_min = settings.cooldown_min_minutes
            original_cooldown_max = settings.cooldown_max_minutes
            settings.hold_min_minutes = 0
            settings.hold_max_minutes = 0
            settings.cooldown_min_minutes = 0
            settings.cooldown_max_minutes = 0

        await run_cycle(settings, reporter, a_client, b_client)
        reporter.write_daily_summary()

        if run_once:
            # Restore settings (not strictly necessary when exiting) and break
            settings.hold_min_minutes = original_hold_min
            settings.hold_max_minutes = original_hold_max
            settings.cooldown_min_minutes = original_cooldown_min
            settings.cooldown_max_minutes = original_cooldown_max
            break

        cooldown = random.randint(settings.cooldown_min_minutes, settings.cooldown_max_minutes)
        await asyncio.sleep(cooldown * 60)

        # Stop after max runtime if requested
        if max_runtime is not None:
            elapsed_min = (datetime.now(UTC) - start_time).total_seconds() / 60.0
            if elapsed_min >= max_runtime:
                print(f"[mode] Reached RUN_MAX_MINUTES={max_runtime}, stopping loop")
                break


if __name__ == "__main__":
    asyncio.run(main())
