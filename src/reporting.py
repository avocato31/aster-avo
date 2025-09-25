from __future__ import annotations

import csv
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import List, Dict, Any

import pytz


@dataclass
class TradeRecord:
    timestamp: str
    cycle_id: str
    symbol: str
    account: str
    side: str
    action: str  # open/close
    quote_usd: float
    executed_qty: float
    avg_price: float


class Reporter:
    def __init__(self, report_dir: str, tz_name: str = "UTC"):
        self.report_dir = report_dir
        self.tz = pytz.timezone(tz_name)
        os.makedirs(self.report_dir, exist_ok=True)

    def _today_filename(self) -> str:
        today = datetime.now(self.tz).strftime("%Y-%m-%d")
        return os.path.join(self.report_dir, f"trades_{today}.csv")

    def write_trade(self, record: TradeRecord) -> None:
        filename = self._today_filename()
        write_header = not os.path.exists(filename)
        with open(filename, mode="a", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "timestamp",
                    "cycle_id",
                    "symbol",
                    "account",
                    "side",
                    "action",
                    "quote_usd",
                    "executed_qty",
                    "avg_price",
                ],
            )
            if write_header:
                writer.writeheader()
            writer.writerow(asdict(record))

    def write_daily_summary(self) -> str:
        """Aggregate today's CSV into a small JSON summary next to it."""
        filename = self._today_filename()
        summary_path = filename.replace(".csv", "_summary.json")
        if not os.path.exists(filename):
            with open(summary_path, "w") as f:
                json.dump({"trades": 0}, f, indent=2)
            return summary_path
        # Aggregate
        total_trades = 0
        symbols: Dict[str, int] = {}
        with open(filename, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                total_trades += 1
                sym = row.get("symbol", "")
                symbols[sym] = symbols.get(sym, 0) + 1
        data = {
            "date": os.path.basename(filename)[7:17],
            "trades": total_trades,
            "by_symbol": symbols,
        }
        with open(summary_path, "w") as f:
            json.dump(data, f, indent=2)
        return summary_path
