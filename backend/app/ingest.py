"""NSE bhavcopy ingest — CM-UDiFF format (post Jul 2024) with legacy fallback."""
from __future__ import annotations

import io
import logging
import subprocess
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import requests

logger = logging.getLogger(__name__)

NIFTY_SYMBOL = "NIFTY"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class NSEDataIngester:
    """Downloads NSE equity bhavcopy from official archives."""

    BASE_URL = "https://nsearchives.nseindia.com"
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.nseindia.com/",
        "Connection": "keep-alive",
    }

    def __init__(self, cache_dir: Path, raw_dir: Path):
        self.cache_dir = cache_dir
        self.raw_dir = raw_dir
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        self._session_initialized = False
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def _init_session(self):
        if self._session_initialized:
            return
        try:
            self.session.get("https://www.nseindia.com", timeout=10)
            time.sleep(0.5)
            self._session_initialized = True
        except Exception as e:
            logger.warning("NSE session init failed: %s", e)

    def _udiff_urls(self, trade_date: datetime) -> list[tuple[str, str]]:
        """New CM-UDiFF Common Bhavcopy Final (since ~Jul 2024)."""
        ymd = trade_date.strftime("%Y%m%d")
        name = f"BhavCopy_NSE_CM_0_0_0_{ymd}_F_0000.csv.zip"
        return [
            (f"{self.BASE_URL}/content/cm/{name}", name),
            (f"https://archives.nseindia.com/content/cm/{name}", name),
        ]

    def _legacy_urls(self, trade_date: datetime) -> list[tuple[str, str]]:
        date_str = trade_date.strftime("%d%b%Y").upper()
        filename = f"cm{date_str}bhav.csv.zip"
        year = trade_date.year
        month = trade_date.strftime("%b").upper()
        return [
            (
                f"{self.BASE_URL}/content/historical/EQUITIES/{year}/{month}/{filename}",
                filename,
            )
        ]

    def _save_zip_bytes(self, content: bytes, filename: str, csv_path: Path) -> Path | None:
        if content[:4] != b"PK\x03\x04":
            return None
        zip_path = self.cache_dir / filename
        zip_path.write_bytes(content)
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            member = zf.namelist()[0]
            csv_path.write_bytes(zf.read(member))
        return csv_path

    def download_bhavcopy(self, trade_date: datetime) -> Path | None:
        candidates = self._udiff_urls(trade_date) + self._legacy_urls(trade_date)

        for url, filename in candidates:
            csv_name = filename.replace(".zip", "")
            csv_path = self.raw_dir / csv_name
            if csv_path.exists():
                return csv_path

            logger.info("Trying bhavcopy %s", url)
            time.sleep(0.3)

            # Prefer curl — more reliable than requests behind some proxies
            try:
                proc = subprocess.run(
                    [
                        "curl",
                        "-sL",
                        "-A",
                        UA,
                        "-H",
                        "Referer: https://www.nseindia.com/",
                        "--max-time",
                        "45",
                        url,
                    ],
                    capture_output=True,
                    check=False,
                )
                if proc.returncode == 0 and proc.stdout:
                    saved = self._save_zip_bytes(proc.stdout, filename, csv_path)
                    if saved:
                        logger.info("Saved bhavcopy via curl %s", csv_path.name)
                        return saved
            except Exception as e:
                logger.warning("curl bhavcopy failed: %s", e)

            try:
                self._init_session()
                response = self.session.get(url, timeout=30)
                if response.status_code == 200:
                    saved = self._save_zip_bytes(response.content, filename, csv_path)
                    if saved:
                        logger.info("Saved bhavcopy via requests %s", csv_path.name)
                        return saved
            except requests.exceptions.RequestException as e:
                logger.warning("Bhavcopy fetch failed %s: %s", trade_date.date(), e)

        logger.warning("No bhavcopy for %s", trade_date.date())
        return None

    def load_bhavcopy_csv(self, path: Path) -> pd.DataFrame:
        df = pd.read_csv(path)
        cols_upper = {c.upper(): c for c in df.columns}

        # New UDiFF schema
        if "TCKRSYMB" in cols_upper or "TckrSymb" in df.columns:
            rename = {
                "TckrSymb": "symbol",
                "SctySrs": "series",
                "OpnPric": "open",
                "HghPric": "high",
                "LwPric": "low",
                "ClsPric": "close",
                "PrvsClsgPric": "prev_close",
                "TtlTradgVol": "volume",
                "TtlTrfVal": "turnover",
                "TradDt": "trade_date",
            }
            df = df.rename(columns=rename)
        else:
            df = df.rename(
                columns={
                    "SYMBOL": "symbol",
                    "OPEN": "open",
                    "HIGH": "high",
                    "LOW": "low",
                    "CLOSE": "close",
                    "PREVCLOSE": "prev_close",
                    "TOTTRDQTY": "volume",
                    "TOTTRDVAL": "turnover",
                    "TIMESTAMP": "trade_date",
                    "SERIES": "series",
                }
            )

        if "series" in df.columns:
            df = df[df["series"] == "EQ"].copy()
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
        cols = [
            "symbol",
            "trade_date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "turnover",
            "prev_close",
        ]
        return df[cols]

    @staticmethod
    def latest_weekday(from_dt: datetime | None = None) -> datetime:
        """Previous trading day (weekends + configured NSE holidays)."""
        from app.nse_calendar import previous_trading_day
        from zoneinfo import ZoneInfo

        IST = ZoneInfo("Asia/Kolkata")
        base = from_dt or datetime.now(IST)
        if base.tzinfo is None:
            base = base.replace(tzinfo=IST)
        prev = previous_trading_day(base.astimezone(IST).date())
        return datetime(prev.year, prev.month, prev.day)

    def ingest_date(self, trade_date: datetime) -> pd.DataFrame:
        path = self.download_bhavcopy(trade_date)
        if path is None:
            return pd.DataFrame()
        return self.load_bhavcopy_csv(path)

    def fill_gap(
        self,
        last_date: str | None,
        end: datetime | None = None,
        max_days: int = 40,
    ) -> list[pd.DataFrame]:
        end_dt = self.latest_weekday(end)
        if last_date:
            start = datetime.strptime(last_date, "%Y-%m-%d") + timedelta(days=1)
        else:
            start = end_dt - timedelta(days=min(max_days, 10))

        frames: list[pd.DataFrame] = []
        current = start
        days_tried = 0
        while current <= end_dt and days_tried < max_days:
            from app.nse_calendar import is_trading_day

            if is_trading_day(current.date()):
                df = self.ingest_date(current)
                if not df.empty:
                    frames.append(df)
                days_tried += 1
            current += timedelta(days=1)
        return frames


def fetch_nifty_history(days: int = 400) -> pd.DataFrame:
    from app.yahoo_eod import days_to_range, fetch_nifty

    return fetch_nifty(range_=days_to_range(days))
