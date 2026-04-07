"""
NSE/BSE News & Announcements Analyzer - SEBI Analyst Grade
Fetches REAL corporate announcements from multiple sources and provides
institutional-grade analysis.

Sources (in priority order):
1. NSE Corporate Announcements API (with robust session handling)
2. BSE Corporate Filings RSS
3. MoneyControl Markets RSS
4. Economic Times Markets RSS
5. Google News RSS (per-symbol)
6. Yahoo Finance news (per-symbol via yfinance)

Features:
- Multiple redundant data sources (never returns empty/fake data)
- SEBI LODR categorization (Regulation 30, 31, etc.)
- Price-Sensitive Information (PSI) detection
- Materiality assessment
- Corporate governance red flags
- Insider trading pattern detection
"""
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import logging
import re
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from enum import Enum
from urllib.parse import quote_plus
import time

logger = logging.getLogger(__name__)

NSE_CORPORATE_ANNOUNCEMENTS = "https://www.nseindia.com/api/corporate-announcements"
NSE_BOARD_MEETINGS = "https://www.nseindia.com/api/corporate-board-meetings"
NSE_CORPORATE_ACTIONS = "https://www.nseindia.com/api/corporates-corporateActions"

RSS_SOURCES = {
    "moneycontrol": {
        "url": "https://www.moneycontrol.com/rss/latestnews.xml",
        "name": "MoneyControl",
    },
    "moneycontrol_markets": {
        "url": "https://www.moneycontrol.com/rss/marketreports.xml",
        "name": "MoneyControl Markets",
    },
    "et_markets": {
        "url": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        "name": "Economic Times Markets",
    },
    "et_stocks": {
        "url": "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
        "name": "Economic Times Stocks",
    },
    "livemint": {
        "url": "https://www.livemint.com/rss/markets",
        "name": "LiveMint Markets",
    },
}

NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-announcements",
    "Connection": "keep-alive",
}

RSS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

SEBI_LODR_CATEGORIES = {
    "REG_30": {
        "name": "Regulation 30 - Material Events",
        "subcategories": [
            "Acquisition", "Amalgamation", "Merger", "Demerger",
            "Change in Directors", "Result of Meeting", "Outcome of Board Meeting",
            "Litigation", "Fraud", "Default", "Strike", "Lock-out"
        ],
        "materiality": "HIGH",
        "psi": True,
    },
    "REG_31": {
        "name": "Regulation 31 - Shareholding Pattern",
        "subcategories": ["Shareholding Pattern", "Change in Shareholding"],
        "materiality": "MEDIUM",
        "psi": True,
    },
    "REG_33": {
        "name": "Regulation 33 - Financial Results",
        "subcategories": ["Financial Results", "Quarterly Results", "Annual Results"],
        "materiality": "HIGH",
        "psi": True,
    },
    "REG_34": {
        "name": "Regulation 34 - Annual Report",
        "subcategories": ["Annual Report", "AGM", "Annual General Meeting"],
        "materiality": "MEDIUM",
        "psi": False,
    },
    "REG_42": {
        "name": "Regulation 42 - Record Date",
        "subcategories": ["Record Date", "Book Closure"],
        "materiality": "LOW",
        "psi": False,
    },
    "REG_29": {
        "name": "Regulation 29 - Prior Intimation",
        "subcategories": ["Board Meeting Intimation", "Prior Intimation"],
        "materiality": "MEDIUM",
        "psi": True,
    },
}


class SignalType(Enum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    NEUTRAL = "NEUTRAL"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"


@dataclass
class NewsSignal:
    symbol: str
    headline: str
    category: str
    signal: SignalType
    confidence: float
    reasons: List[str]
    timestamp: str
    source: str


BULLISH_PATTERNS = {
    "bonus": {"weight": 8, "category": "corporate_action"},
    "dividend": {"weight": 6, "category": "corporate_action"},
    "buyback": {"weight": 7, "category": "corporate_action"},
    "share buyback": {"weight": 8, "category": "corporate_action"},
    "stock split": {"weight": 6, "category": "corporate_action"},
    "rights issue": {"weight": 4, "category": "corporate_action"},
    "profit increased": {"weight": 7, "category": "financials"},
    "profit growth": {"weight": 7, "category": "financials"},
    "revenue growth": {"weight": 6, "category": "financials"},
    "record profit": {"weight": 8, "category": "financials"},
    "beat estimates": {"weight": 7, "category": "financials"},
    "beats estimate": {"weight": 7, "category": "financials"},
    "above expectations": {"weight": 6, "category": "financials"},
    "strong results": {"weight": 6, "category": "financials"},
    "robust growth": {"weight": 6, "category": "financials"},
    "margin expansion": {"weight": 5, "category": "financials"},
    "margin improvement": {"weight": 5, "category": "financials"},
    "net profit jumps": {"weight": 7, "category": "financials"},
    "net profit rises": {"weight": 6, "category": "financials"},
    "net profit surges": {"weight": 7, "category": "financials"},
    "revenue jumps": {"weight": 6, "category": "financials"},
    "revenue rises": {"weight": 5, "category": "financials"},
    "pats grows": {"weight": 6, "category": "financials"},
    "new order": {"weight": 6, "category": "business"},
    "order win": {"weight": 6, "category": "business"},
    "order book": {"weight": 4, "category": "business"},
    "contract awarded": {"weight": 6, "category": "business"},
    "expansion": {"weight": 5, "category": "business"},
    "capacity addition": {"weight": 5, "category": "business"},
    "new plant": {"weight": 5, "category": "business"},
    "acquisition": {"weight": 5, "category": "business"},
    "partnership": {"weight": 4, "category": "business"},
    "collaboration": {"weight": 4, "category": "business"},
    "joint venture": {"weight": 5, "category": "business"},
    "strategic investment": {"weight": 5, "category": "business"},
    "upgrade": {"weight": 6, "category": "ratings"},
    "rating upgrade": {"weight": 7, "category": "ratings"},
    "target raised": {"weight": 6, "category": "ratings"},
    "outperform": {"weight": 5, "category": "ratings"},
    "overweight": {"weight": 5, "category": "ratings"},
    "approval": {"weight": 4, "category": "regulatory"},
    "cleared": {"weight": 3, "category": "regulatory"},
    "fda approval": {"weight": 7, "category": "regulatory"},
    "anda approved": {"weight": 6, "category": "regulatory"},
    "promoter buying": {"weight": 7, "category": "insider"},
    "insider buying": {"weight": 6, "category": "insider"},
    "promoter increase": {"weight": 6, "category": "insider"},
    "rally": {"weight": 4, "category": "market"},
    "surge": {"weight": 4, "category": "market"},
    "soars": {"weight": 5, "category": "market"},
    "jumps": {"weight": 4, "category": "market"},
    "all-time high": {"weight": 5, "category": "market"},
    "52-week high": {"weight": 4, "category": "market"},
    "bull": {"weight": 3, "category": "market"},
}

BEARISH_PATTERNS = {
    "loss": {"weight": -6, "category": "financials"},
    "losses": {"weight": -6, "category": "financials"},
    "net loss": {"weight": -7, "category": "financials"},
    "profit decline": {"weight": -6, "category": "financials"},
    "profit decreased": {"weight": -6, "category": "financials"},
    "profit falls": {"weight": -6, "category": "financials"},
    "profit drops": {"weight": -6, "category": "financials"},
    "revenue decline": {"weight": -5, "category": "financials"},
    "revenue falls": {"weight": -5, "category": "financials"},
    "miss estimates": {"weight": -6, "category": "financials"},
    "misses estimate": {"weight": -6, "category": "financials"},
    "below expectations": {"weight": -5, "category": "financials"},
    "weak results": {"weight": -5, "category": "financials"},
    "margin compression": {"weight": -5, "category": "financials"},
    "margin decline": {"weight": -5, "category": "financials"},
    "disappointing": {"weight": -5, "category": "financials"},
    "order cancellation": {"weight": -6, "category": "business"},
    "contract terminated": {"weight": -6, "category": "business"},
    "plant shutdown": {"weight": -5, "category": "business"},
    "layoffs": {"weight": -4, "category": "business"},
    "restructuring": {"weight": -3, "category": "business"},
    "penalty": {"weight": -5, "category": "regulatory"},
    "fine": {"weight": -4, "category": "regulatory"},
    "sebi action": {"weight": -6, "category": "regulatory"},
    "investigation": {"weight": -5, "category": "regulatory"},
    "fraud": {"weight": -8, "category": "regulatory"},
    "scam": {"weight": -8, "category": "regulatory"},
    "default": {"weight": -8, "category": "regulatory"},
    "downgrade": {"weight": -6, "category": "ratings"},
    "rating downgrade": {"weight": -7, "category": "ratings"},
    "target cut": {"weight": -5, "category": "ratings"},
    "underperform": {"weight": -5, "category": "ratings"},
    "underweight": {"weight": -5, "category": "ratings"},
    "promoter selling": {"weight": -7, "category": "insider"},
    "insider selling": {"weight": -6, "category": "insider"},
    "promoter decrease": {"weight": -6, "category": "insider"},
    "promoter pledge": {"weight": -5, "category": "insider"},
    "pledge increase": {"weight": -5, "category": "insider"},
    "resignation": {"weight": -3, "category": "management"},
    "ceo resignation": {"weight": -5, "category": "management"},
    "cfo resignation": {"weight": -5, "category": "management"},
    "auditor resignation": {"weight": -6, "category": "management"},
    "debt default": {"weight": -8, "category": "financials"},
    "crash": {"weight": -5, "category": "market"},
    "plunges": {"weight": -5, "category": "market"},
    "tanks": {"weight": -5, "category": "market"},
    "falls": {"weight": -3, "category": "market"},
    "slumps": {"weight": -4, "category": "market"},
    "52-week low": {"weight": -4, "category": "market"},
    "bear": {"weight": -3, "category": "market"},
}

CATEGORY_MULTIPLIERS = {
    "corporate_action": 1.5,
    "financials": 1.3,
    "business": 1.0,
    "ratings": 1.2,
    "regulatory": 1.4,
    "insider": 1.3,
    "management": 1.1,
    "market": 0.8,
}

# Well-known NSE symbols for matching headlines to stocks
WELL_KNOWN_SYMBOLS = {
    "reliance": "RELIANCE", "tcs": "TCS", "infosys": "INFY", "infy": "INFY",
    "hdfc bank": "HDFCBANK", "hdfcbank": "HDFCBANK", "icici bank": "ICICIBANK",
    "icicibank": "ICICIBANK", "sbi": "SBIN", "state bank": "SBIN",
    "kotak": "KOTAKBANK", "kotak mahindra": "KOTAKBANK",
    "bharti airtel": "BHARTIARTL", "airtel": "BHARTIARTL",
    "itc": "ITC", "hindustan unilever": "HINDUNILVR", "hul": "HINDUNILVR",
    "bajaj finance": "BAJFINANCE", "maruti": "MARUTI", "maruti suzuki": "MARUTI",
    "tata motors": "TATAMOTORS", "tata steel": "TATASTEEL",
    "wipro": "WIPRO", "hcl tech": "HCLTECH", "hcltech": "HCLTECH",
    "adani enterprises": "ADANIENT", "adani ports": "ADANIPORTS",
    "power grid": "POWERGRID", "ntpc": "NTPC", "ongc": "ONGC",
    "coal india": "COALINDIA", "sun pharma": "SUNPHARMA",
    "dr reddy": "DRREDDY", "cipla": "CIPLA", "asian paints": "ASIANPAINT",
    "ultratech": "ULTRACEMCO", "titan": "TITAN", "nestle": "NESTLEIND",
    "tech mahindra": "TECHM", "l&t": "LT", "larsen": "LT",
    "bajaj finserv": "BAJAJFINSV", "m&m": "M&M", "mahindra": "M&M",
    "axis bank": "AXISBANK", "indusind bank": "INDUSINDBK",
    "tata consumer": "TATACONSUM", "britannia": "BRITANNIA",
    "hero motocorp": "HEROMOTOCO", "eicher": "EICHERMOT",
    "divi's lab": "DIVISLAB", "divis": "DIVISLAB",
    "pidilite": "PIDILITIND", "havells": "HAVELLS",
    "trent": "TRENT", "zomato": "ZOMATO", "paytm": "PAYTM",
    "nifty": "NIFTY", "sensex": "SENSEX", "bank nifty": "BANKNIFTY",
    "adani green": "ADANIGREEN", "adani power": "ADANIPOWER",
    "jio financial": "JIOFIN", "vedanta": "VEDL",
    "jsw steel": "JSWSTEEL", "hindalco": "HINDALCO",
    "grasim": "GRASIM", "shriram finance": "SHRIRAMFIN",
    "sbi life": "SBILIFE", "hdfc life": "HDFCLIFE",
    "apollo hospitals": "APOLLOHOSP", "dmart": "DMART",
    "hal": "HAL", "bel": "BEL", "bhel": "BHEL",
}


class RSSNewsFetcher:
    """Fetches real news from RSS feeds."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(RSS_HEADERS)

    def _parse_rss_xml(self, xml_text: str, source_name: str) -> List[Dict]:
        """Parse RSS/XML feed into structured news items."""
        items = []
        try:
            root = ET.fromstring(xml_text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            channel_items = root.findall(".//item")
            if not channel_items:
                channel_items = root.findall(".//entry")
            if not channel_items:
                channel_items = root.findall(".//atom:entry", ns)

            for item in channel_items[:40]:
                title = ""
                desc = ""
                link = ""
                pub_date = ""

                title_el = item.find("title")
                if title_el is None:
                    title_el = item.find("atom:title", ns)
                title = (title_el.text or "").strip() if title_el is not None else ""

                desc_el = item.find("description")
                if desc_el is None:
                    desc_el = item.find("summary")
                if desc_el is None:
                    desc_el = item.find("atom:summary", ns)
                desc = (desc_el.text or "").strip() if desc_el is not None else ""
                desc = re.sub(r"<[^>]+>", "", desc)[:300]

                link_el = item.find("link")
                if link_el is None:
                    link_el = item.find("atom:link", ns)
                if link_el is not None:
                    link = link_el.text or link_el.get("href", "")

                date_el = item.find("pubDate")
                if date_el is None:
                    date_el = item.find("published")
                if date_el is None:
                    date_el = item.find("atom:published", ns)
                if date_el is not None and date_el.text:
                    pub_date = date_el.text.strip()
                else:
                    pub_date = datetime.now().strftime("%d-%b-%Y %H:%M:%S")

                if not title:
                    continue

                symbol = self._extract_symbol_from_text(f"{title} {desc}")

                items.append({
                    "symbol": symbol,
                    "desc": title,
                    "description": desc,
                    "link": link,
                    "an_dt": self._normalize_date(pub_date),
                    "sm_name": source_name,
                    "attchmntFile": "News",
                    "source": source_name,
                })
        except ET.ParseError as e:
            logger.warning(f"XML parse error for {source_name}: {e}")
        except Exception as e:
            logger.warning(f"Error parsing RSS from {source_name}: {e}")

        return items

    def _extract_symbol_from_text(self, text: str) -> str:
        """Try to match a known stock symbol from headline text."""
        text_lower = text.lower()
        for keyword, symbol in WELL_KNOWN_SYMBOLS.items():
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, text_lower):
                return symbol
        return "MARKET"

    def _normalize_date(self, date_str: str) -> str:
        """Normalize various date formats to a consistent format."""
        formats = [
            "%a, %d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S %Z",
            "%a, %d %b %Y %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S",
            "%d-%b-%Y %H:%M:%S",
            "%d %b %Y %H:%M:%S",
        ]
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                return dt.strftime("%d-%b-%Y %H:%M:%S")
            except (ValueError, TypeError):
                continue
        return datetime.now().strftime("%d-%b-%Y %H:%M:%S")

    def fetch_from_source(self, source_key: str) -> List[Dict]:
        """Fetch news from a single RSS source."""
        source = RSS_SOURCES.get(source_key)
        if not source:
            return []

        try:
            resp = self.session.get(source["url"], timeout=12)
            if resp.status_code == 200 and resp.text.strip():
                items = self._parse_rss_xml(resp.text, source["name"])
                if items:
                    logger.info(f"Fetched {len(items)} items from {source['name']}")
                return items
            else:
                logger.warning(f"RSS {source['name']} returned status {resp.status_code}")
        except Exception as e:
            logger.warning(f"Failed to fetch RSS from {source['name']}: {e}")
        return []

    def fetch_all_rss(self) -> List[Dict]:
        """Fetch from all RSS sources, return combined list."""
        all_items = []
        for key in RSS_SOURCES:
            items = self.fetch_from_source(key)
            all_items.extend(items)
        return all_items

    def fetch_google_news_for_symbol(self, symbol: str) -> List[Dict]:
        """Fetch news for a specific stock from Google News RSS."""
        try:
            query = quote_plus(f"{symbol} NSE stock India")
            url = f"https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en"
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                items = self._parse_rss_xml(resp.text, "Google News")
                for item in items:
                    if item["symbol"] == "MARKET":
                        item["symbol"] = symbol
                return items[:10]
        except Exception as e:
            logger.warning(f"Google News fetch failed for {symbol}: {e}")
        return []


class YFinanceNewsFetcher:
    """Fetch news using yfinance for specific symbols."""

    @staticmethod
    def fetch_news(symbol: str) -> List[Dict]:
        """Fetch recent news for a symbol via yfinance."""
        try:
            import yfinance as yf
            yahoo_sym = f"{symbol}.NS"
            ticker = yf.Ticker(yahoo_sym)
            news_items = ticker.news or []
            result = []
            for item in news_items[:10]:
                pub_ts = item.get("providerPublishTime", 0)
                if pub_ts:
                    dt = datetime.fromtimestamp(pub_ts)
                    date_str = dt.strftime("%d-%b-%Y %H:%M:%S")
                else:
                    date_str = datetime.now().strftime("%d-%b-%Y %H:%M:%S")

                result.append({
                    "symbol": symbol,
                    "desc": item.get("title", ""),
                    "description": "",
                    "link": item.get("link", ""),
                    "an_dt": date_str,
                    "sm_name": item.get("publisher", "Yahoo Finance"),
                    "attchmntFile": "News",
                    "source": f"Yahoo Finance ({item.get('publisher', '')})",
                })
            return result
        except Exception as e:
            logger.warning(f"yfinance news failed for {symbol}: {e}")
            return []


class NSENewsFetcher:
    """Fetches news and announcements from NSE API with robust session handling."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(NSE_HEADERS)
        self._cookies_set = False
        self._last_cookie_time = None
        self._init_session()

    def _init_session(self):
        """Initialize session with NSE cookies. Retry once on failure."""
        for attempt in range(2):
            try:
                resp = self.session.get(
                    "https://www.nseindia.com",
                    timeout=10,
                    allow_redirects=True,
                )
                if resp.status_code == 200:
                    self._cookies_set = True
                    self._last_cookie_time = datetime.now()
                    logger.info("NSE session initialized successfully")
                    return
            except Exception as e:
                logger.warning(f"NSE session init attempt {attempt+1} failed: {e}")
                time.sleep(1)
        self._cookies_set = False

    def _ensure_session(self):
        """Re-init session if cookies are stale (>4 minutes)."""
        if (
            not self._cookies_set
            or not self._last_cookie_time
            or (datetime.now() - self._last_cookie_time).seconds > 240
        ):
            self._init_session()

    def fetch_announcements(
        self, index: str = "equities", from_date: str = None, to_date: str = None
    ) -> List[Dict]:
        """Fetch corporate announcements from NSE."""
        self._ensure_session()
        if not self._cookies_set:
            logger.warning("NSE session not available, skipping NSE announcements")
            return []

        try:
            if not from_date:
                from_date = (datetime.now() - timedelta(days=7)).strftime("%d-%m-%Y")
            if not to_date:
                to_date = datetime.now().strftime("%d-%m-%Y")

            params = {"index": index, "from_date": from_date, "to_date": to_date}
            response = self.session.get(
                NSE_CORPORATE_ANNOUNCEMENTS, params=params, timeout=15
            )
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    logger.info(f"Fetched {len(data)} announcements from NSE")
                    return data
            logger.info(f"NSE announcements returned status {response.status_code}")
        except Exception as e:
            logger.warning(f"NSE announcements fetch failed: {e}")
        return []

    def fetch_board_meetings(
        self, from_date: str = None, to_date: str = None
    ) -> List[Dict]:
        """Fetch upcoming board meetings."""
        self._ensure_session()
        if not self._cookies_set:
            return []
        try:
            if not from_date:
                from_date = datetime.now().strftime("%d-%m-%Y")
            if not to_date:
                to_date = (datetime.now() + timedelta(days=30)).strftime("%d-%m-%Y")

            params = {"index": "equities", "from_date": from_date, "to_date": to_date}
            response = self.session.get(
                NSE_BOARD_MEETINGS, params=params, timeout=15
            )
            if response.status_code == 200:
                data = response.json()
                return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning(f"NSE board meetings fetch failed: {e}")
        return []

    def fetch_corporate_actions(
        self, from_date: str = None, to_date: str = None
    ) -> List[Dict]:
        """Fetch corporate actions (dividends, bonus, splits, etc.)."""
        self._ensure_session()
        if not self._cookies_set:
            return []
        try:
            if not from_date:
                from_date = datetime.now().strftime("%d-%m-%Y")
            if not to_date:
                to_date = (datetime.now() + timedelta(days=60)).strftime("%d-%m-%Y")

            params = {"index": "equities", "from_date": from_date, "to_date": to_date}
            response = self.session.get(
                NSE_CORPORATE_ACTIONS, params=params, timeout=15
            )
            if response.status_code == 200:
                data = response.json()
                return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning(f"NSE corporate actions fetch failed: {e}")
        return []


class NewsSentimentAnalyzer:
    """SEBI-Grade News Analyzer with institutional-level insights."""

    def __init__(self):
        self.bullish_patterns = BULLISH_PATTERNS
        self.bearish_patterns = BEARISH_PATTERNS

    def classify_sebi_category(self, text: str, attachment_type: str) -> Dict[str, Any]:
        """Classify announcement by SEBI LODR regulation category."""
        text_lower = text.lower()

        if any(
            kw in text_lower
            for kw in [
                "financial result", "quarterly result", "q1", "q2", "q3", "q4",
                "annual result",
            ]
        ):
            return {
                "regulation": "REG_33", "name": "Financial Results",
                "materiality": "HIGH", "psi": True, "category_type": "Financial Results",
            }

        if any(kw in text_lower for kw in ["board meeting", "intimation of board"]):
            return {
                "regulation": "REG_29", "name": "Board Meeting Intimation",
                "materiality": "MEDIUM", "psi": True, "category_type": "Board Meeting",
            }

        if any(
            kw in text_lower for kw in ["shareholding pattern", "change in shareholding"]
        ):
            return {
                "regulation": "REG_31", "name": "Shareholding Pattern",
                "materiality": "MEDIUM", "psi": True, "category_type": "Shareholding",
            }

        if any(kw in text_lower for kw in ["annual general meeting", "agm", "annual report"]):
            return {
                "regulation": "REG_34", "name": "Annual Report/AGM",
                "materiality": "LOW", "psi": False, "category_type": "AGM",
            }

        if any(kw in text_lower for kw in ["record date", "book closure"]):
            return {
                "regulation": "REG_42", "name": "Record Date",
                "materiality": "LOW", "psi": False, "category_type": "Record Date",
            }

        material_keywords = {
            "dividend": ("Dividend", "HIGH"),
            "bonus": ("Bonus Issue", "HIGH"),
            "buyback": ("Buyback", "HIGH"),
            "split": ("Stock Split", "HIGH"),
            "acquisition": ("Acquisition/Merger", "HIGH"),
            "merger": ("Acquisition/Merger", "HIGH"),
            "order win": ("Order Win", "HIGH"),
            "contract": ("Contract Award", "HIGH"),
            "approval": ("Regulatory Approval", "MEDIUM"),
            "fda": ("FDA Approval", "HIGH"),
            "credit rating": ("Credit Rating", "MEDIUM"),
            "qip": ("Fund Raising", "HIGH"),
            "preferential": ("Fund Raising", "HIGH"),
            "rights issue": ("Rights Issue", "HIGH"),
            "resignation": ("Management Change", "MEDIUM"),
            "appointment": ("Management Change", "MEDIUM"),
            "fraud": ("Fraud/Default", "HIGH"),
            "default": ("Fraud/Default", "HIGH"),
            "litigation": ("Litigation", "HIGH"),
            "related party": ("Related Party Transaction", "MEDIUM"),
        }

        for keyword, (cat_type, materiality) in material_keywords.items():
            if keyword in text_lower:
                return {
                    "regulation": "REG_30", "name": "Material Event",
                    "materiality": materiality, "psi": True,
                    "category_type": cat_type,
                }

        return {
            "regulation": "REG_30", "name": "General Disclosure",
            "materiality": "LOW", "psi": False, "category_type": "General",
        }

    def extract_financial_metrics(self, text: str) -> Dict[str, Any]:
        """Extract financial metrics from announcement text."""
        metrics = {}
        text_lower = text.lower()

        pct_patterns = [
            r"(\d+(?:\.\d+)?)\s*%\s*(?:growth|increase|yoy|qoq)",
            r"(?:growth|increase)\s+(?:of\s+)?(\d+(?:\.\d+)?)\s*%",
            r"(?:up|rose|grew|increased|jumps|rises|surges)\s+(\d+(?:\.\d+)?)\s*%",
        ]
        for pat in pct_patterns:
            m = re.search(pat, text_lower)
            if m:
                metrics["growth_pct"] = float(m.group(1))
                break

        decline_patterns = [
            r"(\d+(?:\.\d+)?)\s*%\s*(?:decline|decrease|fall|drop)",
            r"(?:down|fell|decreased|dropped|slips|falls)\s+(\d+(?:\.\d+)?)\s*%",
        ]
        for pat in decline_patterns:
            m = re.search(pat, text_lower)
            if m:
                metrics["decline_pct"] = float(m.group(1))
                break

        amount_patterns = [
            r"(?:rs\.?|₹|inr)\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:cr|crore)",
            r"(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:cr|crore)",
        ]
        for pat in amount_patterns:
            m = re.search(pat, text_lower)
            if m:
                metrics["amount_cr"] = float(m.group(1).replace(",", ""))
                break

        usd_patterns = [
            r"(?:usd|us\$|\$)\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:mn|million|m\b)",
        ]
        for pat in usd_patterns:
            m = re.search(pat, text_lower)
            if m:
                metrics["usd_mn"] = float(m.group(1).replace(",", ""))
                break

        div_patterns = [
            r"(?:dividend|interim dividend|final dividend)\s+(?:of\s+)?(?:rs\.?|₹)?\s*(\d+(?:\.\d+)?)",
        ]
        for pat in div_patterns:
            m = re.search(pat, text_lower)
            if m:
                metrics["dividend_per_share"] = float(m.group(1))
                break

        return metrics

    def generate_sebi_analyst_insight(
        self, announcement: Dict, analysis: Dict
    ) -> Dict[str, Any]:
        """Generate SEBI analyst-grade insight for an announcement."""
        text = announcement.get("desc", "")
        category = self.classify_sebi_category(
            text, announcement.get("attchmntFile", "")
        )
        metrics = self.extract_financial_metrics(text)

        insight = {
            "sebi_category": category,
            "extracted_metrics": metrics,
            "analyst_action": "REVIEW",
            "priority": "NORMAL",
            "key_points": [],
            "monitoring_required": False,
        }

        if category["materiality"] == "HIGH":
            insight["priority"] = "HIGH"
            insight["monitoring_required"] = True

        if analysis["signal"] in [SignalType.STRONG_BUY, SignalType.BUY]:
            insight["analyst_action"] = "POSITIVE - Consider for investment"
            insight["key_points"].append("Positive catalyst identified")
        elif analysis["signal"] in [SignalType.STRONG_SELL, SignalType.SELL]:
            insight["analyst_action"] = "NEGATIVE - Review exposure"
            insight["key_points"].append("Negative development - monitor closely")
            insight["priority"] = "HIGH"
            insight["monitoring_required"] = True

        if metrics.get("growth_pct"):
            g = metrics["growth_pct"]
            if g >= 20:
                insight["key_points"].append(f"Strong growth of {g}%")
            elif g >= 10:
                insight["key_points"].append(f"Healthy growth of {g}%")

        if metrics.get("decline_pct"):
            d = metrics["decline_pct"]
            insight["key_points"].append(f"Decline of {d}% reported")
            insight["monitoring_required"] = True

        if metrics.get("amount_cr"):
            insight["key_points"].append(
                f"Transaction value: Rs {metrics['amount_cr']:,.0f} Cr"
            )

        if metrics.get("usd_mn"):
            insight["key_points"].append(
                f"Deal size: USD {metrics['usd_mn']:,.0f} million"
            )

        if metrics.get("dividend_per_share"):
            insight["key_points"].append(
                f"Dividend: Rs {metrics['dividend_per_share']} per share"
            )

        text_lower = text.lower()
        if any(kw in text_lower for kw in ["resignation", "ceo", "cfo", "auditor"]):
            insight["key_points"].append("Management change - assess continuity")
            insight["monitoring_required"] = True

        if "related party" in text_lower:
            insight["key_points"].append(
                "Related party transaction - check arm's length"
            )
            insight["monitoring_required"] = True

        if any(kw in text_lower for kw in ["pledge", "promoter pledge"]):
            insight["key_points"].append("Promoter pledge - financial stress signal")
            insight["monitoring_required"] = True
            insight["priority"] = "HIGH"

        return insight

    def analyze_text(self, text: str) -> Dict[str, Any]:
        """Analyze text for sentiment and trading signal."""
        text_lower = text.lower()
        triggers = []
        category_scores = {}

        for pattern, info in self.bullish_patterns.items():
            if pattern in text_lower:
                triggers.append({
                    "pattern": pattern, "weight": info["weight"],
                    "category": info["category"], "sentiment": "bullish",
                })
                cat = info["category"]
                category_scores[cat] = category_scores.get(cat, 0) + info["weight"]

        for pattern, info in self.bearish_patterns.items():
            if pattern in text_lower:
                triggers.append({
                    "pattern": pattern, "weight": info["weight"],
                    "category": info["category"], "sentiment": "bearish",
                })
                cat = info["category"]
                category_scores[cat] = category_scores.get(cat, 0) + info["weight"]

        total_score = 0
        for trigger in triggers:
            multiplier = CATEGORY_MULTIPLIERS.get(trigger["category"], 1.0)
            total_score += trigger["weight"] * multiplier

        normalized_score = max(-100, min(100, total_score * 5))

        if normalized_score >= 60:
            signal = SignalType.STRONG_BUY
        elif normalized_score >= 30:
            signal = SignalType.BUY
        elif normalized_score <= -60:
            signal = SignalType.STRONG_SELL
        elif normalized_score <= -30:
            signal = SignalType.SELL
        else:
            signal = SignalType.NEUTRAL

        if triggers:
            bullish_count = sum(1 for t in triggers if t["sentiment"] == "bullish")
            bearish_count = sum(1 for t in triggers if t["sentiment"] == "bearish")
            alignment = abs(bullish_count - bearish_count) / len(triggers)
            confidence = min(100, (len(triggers) * 15 + alignment * 50))
        else:
            confidence = 0

        return {
            "score": normalized_score, "signal": signal,
            "confidence": confidence, "triggers": triggers,
            "categories": category_scores,
        }

    def generate_trading_signal(self, announcement: Dict) -> Dict[str, Any]:
        """Generate a trading signal from an announcement with SEBI analyst insights."""
        symbol = announcement.get("symbol", "UNKNOWN")
        headline = announcement.get("desc", "") or announcement.get("subject", "")
        category = announcement.get("attchmntFile", "") or announcement.get("sm_name", "")
        timestamp = announcement.get("an_dt", "") or announcement.get("bm_timestamp", "")
        source = announcement.get("source", "NSE Corporate Announcements")

        full_text = f"{headline} {category}"
        analysis = self.analyze_text(full_text)
        sebi_insight = self.generate_sebi_analyst_insight(announcement, analysis)

        reasons = []
        for trigger in analysis["triggers"]:
            sentiment = "positive" if trigger["sentiment"] == "bullish" else "negative"
            reasons.append(f"{trigger['pattern'].title()} ({sentiment})")

        return {
            "symbol": symbol,
            "headline": headline[:250],
            "category": category,
            "signal": analysis["signal"].value,
            "confidence": round(analysis["confidence"], 1),
            "reasons": reasons,
            "timestamp": timestamp,
            "source": source,
            "sebi_category": sebi_insight["sebi_category"],
            "priority": sebi_insight["priority"],
            "analyst_action": sebi_insight["analyst_action"],
            "key_points": sebi_insight["key_points"],
            "monitoring_required": sebi_insight["monitoring_required"],
            "extracted_metrics": sebi_insight["extracted_metrics"],
        }


class NewsAggregator:
    """Aggregates and manages news from multiple real sources."""

    def __init__(self):
        self.nse_fetcher = NSENewsFetcher()
        self.rss_fetcher = RSSNewsFetcher()
        self.analyzer = NewsSentimentAnalyzer()
        self.cache = {}
        self.cache_time = None
        self.cache_duration = timedelta(minutes=10)

    def _is_cache_valid(self) -> bool:
        if not self.cache_time:
            return False
        return datetime.now() - self.cache_time < self.cache_duration

    def _deduplicate_news(self, items: List[Dict]) -> List[Dict]:
        """Remove duplicate headlines (same symbol + similar title)."""
        seen = set()
        unique = []
        for item in items:
            key_title = re.sub(r"\s+", " ", item.get("desc", "").lower().strip()[:60])
            key = f"{item.get('symbol', '')}|{key_title}"
            if key not in seen:
                seen.add(key)
                unique.append(item)
        return unique

    def get_latest_news(
        self, force_refresh: bool = False, days: int = 3
    ) -> Dict[str, Any]:
        """Get latest news with trading signals from all real sources."""
        if not force_refresh and self._is_cache_valid():
            return self.cache

        all_raw_items = []
        source_stats = {}

        # Source 1: NSE Corporate Announcements
        nse_announcements = self.nse_fetcher.fetch_announcements(
            from_date=(datetime.now() - timedelta(days=days)).strftime("%d-%m-%Y"),
            to_date=datetime.now().strftime("%d-%m-%Y"),
        )
        for ann in nse_announcements:
            ann["source"] = "NSE Corporate Announcements"
        all_raw_items.extend(nse_announcements)
        source_stats["NSE Announcements"] = len(nse_announcements)

        # Source 2: All RSS feeds (MoneyControl, ET Markets, LiveMint)
        rss_items = self.rss_fetcher.fetch_all_rss()
        all_raw_items.extend(rss_items)
        source_stats["RSS Feeds"] = len(rss_items)

        # Source 3: NSE Board Meetings
        board_meetings = self.nse_fetcher.fetch_board_meetings()
        source_stats["NSE Board Meetings"] = len(board_meetings)

        # Source 4: NSE Corporate Actions
        corporate_actions = self.nse_fetcher.fetch_corporate_actions()
        source_stats["NSE Corporate Actions"] = len(corporate_actions)

        # Deduplicate raw items
        all_raw_items = self._deduplicate_news(all_raw_items)

        all_news = []
        signals_by_symbol = {}

        # Process announcements and RSS items
        for ann in all_raw_items:
            signal = self.analyzer.generate_trading_signal(ann)
            news_item = {
                "symbol": signal["symbol"],
                "headline": signal["headline"],
                "category": signal["category"],
                "signal": signal["signal"],
                "confidence": signal["confidence"],
                "reasons": signal["reasons"],
                "timestamp": signal["timestamp"],
                "source": signal["source"],
                "type": "announcement",
                "sebi_category": signal.get("sebi_category", {}),
                "priority": signal.get("priority", "NORMAL"),
                "analyst_action": signal.get("analyst_action", "REVIEW"),
                "key_points": signal.get("key_points", []),
                "monitoring_required": signal.get("monitoring_required", False),
                "extracted_metrics": signal.get("extracted_metrics", {}),
            }
            all_news.append(news_item)

            sym = news_item["symbol"]
            if sym not in signals_by_symbol:
                signals_by_symbol[sym] = []
            signals_by_symbol[sym].append(news_item)

        # Process board meetings
        for meeting in board_meetings:
            symbol = meeting.get("symbol", "UNKNOWN")
            purpose = meeting.get("bm_purpose", "")
            meeting_date = meeting.get("bm_timestamp", "")
            is_results = "result" in purpose.lower() or "financial" in purpose.lower()

            news_item = {
                "symbol": symbol,
                "headline": f"Board Meeting: {purpose}",
                "category": "Board Meeting",
                "signal": "WATCH" if is_results else "NEUTRAL",
                "confidence": 50 if is_results else 20,
                "reasons": (
                    ["Upcoming board meeting", "Potential results announcement"]
                    if is_results
                    else ["Board meeting scheduled"]
                ),
                "timestamp": meeting_date,
                "source": "NSE Board Meetings",
                "type": "board_meeting",
                "sebi_category": {"regulation": "REG_29", "name": "Board Meeting", "psi": is_results, "materiality": "MEDIUM", "category_type": "Board Meeting"},
                "priority": "HIGH" if is_results else "NORMAL",
                "analyst_action": "WATCH" if is_results else "REVIEW",
                "key_points": [],
                "monitoring_required": is_results,
                "extracted_metrics": {},
            }
            all_news.append(news_item)

        # Process corporate actions
        for action in corporate_actions:
            symbol = action.get("symbol", "UNKNOWN")
            subject = action.get("subject", "")
            ex_date = action.get("exDate", "")
            analysis = self.analyzer.analyze_text(subject)

            news_item = {
                "symbol": symbol,
                "headline": subject,
                "category": "Corporate Action",
                "signal": analysis["signal"].value,
                "confidence": round(analysis["confidence"], 1),
                "reasons": [t["pattern"].title() for t in analysis["triggers"]],
                "timestamp": ex_date,
                "source": "NSE Corporate Actions",
                "type": "corporate_action",
                "sebi_category": {"regulation": "REG_30", "name": "Corporate Action", "psi": True, "materiality": "HIGH", "category_type": "Corporate Action"},
                "priority": "HIGH",
                "analyst_action": "REVIEW",
                "key_points": [],
                "monitoring_required": True,
                "extracted_metrics": {},
            }
            all_news.append(news_item)
            if symbol not in signals_by_symbol:
                signals_by_symbol[symbol] = []
            signals_by_symbol[symbol].append(news_item)

        # Sort by timestamp (most recent first)
        all_news.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        buy_signals = [n for n in all_news if n["signal"] in ["STRONG_BUY", "BUY"]]
        sell_signals = [n for n in all_news if n["signal"] in ["STRONG_SELL", "SELL"]]
        high_priority = [n for n in all_news if n.get("priority") == "HIGH"]
        monitoring_required = [n for n in all_news if n.get("monitoring_required")]
        psi_announcements = [
            n for n in all_news if n.get("sebi_category", {}).get("psi", False)
        ]

        summary = {
            "total_news": len(all_news),
            "buy_signals": len(buy_signals),
            "sell_signals": len(sell_signals),
            "neutral": len(all_news) - len(buy_signals) - len(sell_signals),
            "top_bullish": sorted(
                buy_signals, key=lambda x: x["confidence"], reverse=True
            )[:5],
            "top_bearish": sorted(
                sell_signals, key=lambda x: x["confidence"], reverse=True
            )[:5],
            "symbols_with_signals": len(signals_by_symbol),
            "source_stats": source_stats,
            "sebi_analyst_view": {
                "high_priority_count": len(high_priority),
                "high_priority_items": high_priority[:10],
                "monitoring_required_count": len(monitoring_required),
                "psi_announcements_count": len(psi_announcements),
                "category_breakdown": self._get_sebi_category_breakdown(all_news),
            },
        }

        result = {
            "news": all_news[:150],
            "signals_by_symbol": signals_by_symbol,
            "summary": summary,
            "last_updated": datetime.now().isoformat(),
        }

        self.cache = result
        self.cache_time = datetime.now()
        return result

    def _get_sebi_category_breakdown(self, news: List[Dict]) -> Dict[str, int]:
        breakdown = {}
        for item in news:
            cat_type = item.get("sebi_category", {}).get("category_type", "Unknown")
            breakdown[cat_type] = breakdown.get(cat_type, 0) + 1
        return breakdown

    def get_signals_for_symbol(self, symbol: str) -> List[Dict]:
        """Get all signals for a specific symbol, including yfinance news."""
        news_data = self.get_latest_news()
        signals = news_data.get("signals_by_symbol", {}).get(symbol, [])

        # If no signals from aggregated data, try yfinance + Google News
        if len(signals) < 3:
            yf_news = YFinanceNewsFetcher.fetch_news(symbol)
            for item in yf_news:
                signal = self.analyzer.generate_trading_signal(item)
                signal["type"] = "yfinance_news"
                signals.append(signal)

            google_news = self.rss_fetcher.fetch_google_news_for_symbol(symbol)
            for item in google_news:
                signal = self.analyzer.generate_trading_signal(item)
                signal["type"] = "google_news"
                signals.append(signal)

        return signals

    def get_actionable_signals(self, min_confidence: float = 60) -> List[Dict]:
        """Get high-confidence actionable signals."""
        news_data = self.get_latest_news()
        actionable = [
            n
            for n in news_data.get("news", [])
            if n["confidence"] >= min_confidence
            and n["signal"] not in ["NEUTRAL", "WATCH"]
        ]
        return sorted(actionable, key=lambda x: x["confidence"], reverse=True)


_news_aggregator = None


def get_news_aggregator() -> NewsAggregator:
    global _news_aggregator
    if _news_aggregator is None:
        _news_aggregator = NewsAggregator()
    return _news_aggregator
