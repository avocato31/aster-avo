from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List
from dotenv import load_dotenv


load_dotenv()


def _get_list(env_key: str, default: List[str]) -> List[str]:
    raw = os.getenv(env_key, "")
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return parts if parts else list(default)


@dataclass
class Settings:
    account_a_api_key: str
    account_a_api_secret: str
    account_b_api_key: str
    account_b_api_secret: str

    base_url: str
    fapi_base_url: str

    # Aster V3 auth (futures) - separate for A and B
    aster_user_a: str
    aster_signer_a: str
    aster_private_key_a: str
    aster_user_b: str
    aster_signer_b: str
    aster_private_key_b: str

    # HMAC keys for USER_DATA
    hmac_api_key_a: str
    hmac_api_secret_a: str
    hmac_api_key_b: str
    hmac_api_secret_b: str

    symbols: List[str]

    min_usd: float
    max_usd: float

    hold_min_minutes: int
    hold_max_minutes: int

    cooldown_min_minutes: int
    cooldown_max_minutes: int

    tz: str
    report_dir: str

    @staticmethod
    def load() -> "Settings":
        symbols = _get_list("SYMBOLS", ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"])
        min_usd = float(os.getenv("MIN_USD", "100"))
        max_usd = float(os.getenv("MAX_USD", "500"))
        if max_usd < min_usd:
            raise ValueError("MAX_USD, MIN_USD'den kucuk olamaz")
        # Backward compatibility: if only single set provided, use for both
        a_user = os.getenv("ASTER_USER_A") or os.getenv("ASTER_USER", "")
        a_signer = os.getenv("ASTER_SIGNER_A") or os.getenv("ASTER_SIGNER") or a_user
        a_pk = os.getenv("ASTER_PRIVATE_KEY_A") or os.getenv("ASTER_PRIVATE_KEY", "")
        b_user = os.getenv("ASTER_USER_B") or os.getenv("ASTER_USER", "")
        b_signer = os.getenv("ASTER_SIGNER_B") or os.getenv("ASTER_SIGNER") or b_user
        b_pk = os.getenv("ASTER_PRIVATE_KEY_B") or os.getenv("ASTER_PRIVATE_KEY", "")

        # HMAC keys - prefer per-account; fallback to single ASTER_API_KEY/SECRET
        hmac_key_a = os.getenv("HMAC_API_KEY_A") or os.getenv("ASTER_API_KEY", "")
        hmac_sec_a = os.getenv("HMAC_API_SECRET_A") or os.getenv("ASTER_API_SECRET", "")
        hmac_key_b = os.getenv("HMAC_API_KEY_B") or os.getenv("ASTER_API_KEY", "")
        hmac_sec_b = os.getenv("HMAC_API_SECRET_B") or os.getenv("ASTER_API_SECRET", "")

        # Base URLs - prefer FAPI_BASE_URL, fallback to ASTER_BASE_URL
        fapi_base = os.getenv("FAPI_BASE_URL") or os.getenv("ASTER_BASE_URL") or "https://fapi.asterdex.com"
        return Settings(
            account_a_api_key=os.getenv("ACCOUNT_A_API_KEY", ""),
            account_a_api_secret=os.getenv("ACCOUNT_A_API_SECRET", ""),
            account_b_api_key=os.getenv("ACCOUNT_B_API_KEY", ""),
            account_b_api_secret=os.getenv("ACCOUNT_B_API_SECRET", ""),
            base_url=os.getenv("BASE_URL", "https://api.placeholder.com"),
            fapi_base_url=fapi_base,
            aster_user_a=a_user,
            aster_signer_a=a_signer,
            aster_private_key_a=a_pk,
            aster_user_b=b_user,
            aster_signer_b=b_signer,
            aster_private_key_b=b_pk,
            hmac_api_key_a=hmac_key_a,
            hmac_api_secret_a=hmac_sec_a,
            hmac_api_key_b=hmac_key_b,
            hmac_api_secret_b=hmac_sec_b,
            symbols=symbols,
            min_usd=min_usd,
            max_usd=max_usd,
            hold_min_minutes=int(os.getenv("HOLD_MIN_MINUTES", "30")),
            hold_max_minutes=int(os.getenv("HOLD_MAX_MINUTES", "180")),
            cooldown_min_minutes=int(os.getenv("COOLDOWN_MIN_MINUTES", "1")),
            cooldown_max_minutes=int(os.getenv("COOLDOWN_MAX_MINUTES", "5")),
            tz=os.getenv("TZ", "UTC"),
            report_dir=os.getenv("REPORT_DIR", "reports"),
        )
