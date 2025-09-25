# hedged aster bot

Basit hedge bot iskeleti. Iki hesapla market emirlerle long/short acip, belirlenen sure tutar, sonra kapatir. Her donguden sonra 1-5 dk arasi bekler.

## Kurulum (Mainnet)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Konfigurasyon
`.env` icindeki ana degiskenler (yalnizca mainnet):
- `FAPI_BASE_URL`: `https://fapi.asterdex.com`
- `HMAC_API_KEY_A`, `HMAC_API_SECRET_A` (Hesap A)
- `HMAC_API_KEY_B`, `HMAC_API_SECRET_B` (Hesap B)
- (Opsiyonel) `ASTER_USER_A|B`, `ASTER_SIGNER_A|B`, `ASTER_PRIVATE_KEY_A|B` (HMAC yoksa kullanilir)
- `SYMBOLS`: virgulle ayrik pariteler (ornegin `BTCUSDT,ETHUSDT,...`)
- `MIN_USD` / `MAX_USD`: 100-500 arasi
- `HOLD_MIN_MINUTES` / `HOLD_MAX_MINUTES`: 30-180 arasi
- `COOLDOWN_MIN_MINUTES` / `COOLDOWN_MAX_MINUTES`: 1-5 arasi

## Calistirma
```bash
PYTHONPATH=. python -m src.bot
```

## API entegrasyonu
Oncelik sirasi:
1) HMAC v1 (V3'e gore daha basit ve dogrudan). `HMAC_API_KEY_*`/`SECRET_*` varsa kullanilir.
2) EVM imzali V3 (kullanim icin `ASTER_USER_*` ve `ASTER_PRIVATE_KEY_*`).
3) Hicbiri yoksa `src/api/stub_client.py` ile stub calisir (yalnizca gelistirme/kurugosteri).

Bu urun yalnizca mainnet icin hazirlanmistir. Testnet desteklenmez.

## Raporlama
Gunun CSV kaydi `reports/trades_YYYY-MM-DD.csv`. Ayrica `*_summary.json` ozet dosyasi uretilir.
