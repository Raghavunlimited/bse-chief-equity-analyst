"""
Kotak Neo HS/apifeed ``native_batch`` binary decoder (little-endian, packed).

Note: Kotak's newer "SFeed" product is a separate migration track (deadline
announced as 15 Sep 2026). This module decodes the current apifeed HS
native_batch layout used by ``ws_client`` — not a claim of SFeed readiness.

Control plane (JSON) is handled by the WebSocket client. This module only
splits batches and decodes binary packets into typed messages.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Any, Optional, Union

HEADER_SIZE = 9
DEFAULT_DIVIDER = 100

MSG_AUTH_OK = 1117
MSG_AUTH_CONNECT = 1119
MSG_AUTH_FAIL = 1120
MSG_AUTH_RESPONSE_CODES = (MSG_AUTH_OK, MSG_AUTH_CONNECT)
MSG_SUBSCRIBE_ACK = 1109
MSG_MARKET_OPEN = 6511
MSG_MARKET_CLOSE = 6521
MSG_INDEX = 7207
MSG_MARKET_PICTURE = 7208
MSG_MARKET_STATUS = 105
MSG_CAS_CHANGE = 104

EXCHANGE_NAME_TO_ID: dict[str, int] = {
    "none": 0,
    "nse_cm": 1,
    "nse_fo": 2,
    "cde_fo": 3,
    "nse_com": 4,
    "bse_cm": 5,
    "bse_fo": 6,
    "bse_cd": 7,
    "bse_co": 8,
    "mcx_fo": 9,
    "ncd_co": 10,
}
EXCHANGE_ID_TO_NAME: dict[int, str] = {v: k for k, v in EXCHANGE_NAME_TO_ID.items()}

LEVEL_MINI = 1
LEVEL_TOUCH = 4
LEVEL_DEPTH = 8
LEVEL_FULL_DEPTH = 16

MARKET_STATUS_TEXT: dict[int, str] = {
    1: "Market open",
    2: "Market closed",
    3: "Pre-open session ending",
    4: "Pre-open ended, normal market open",
    5: "Auction status changed",
    6: "Closing session started",
    7: "Closing session ended",
    8: "Continuous trading closed, closing auction starting soon",
    9: "Closing auction price band set",
    10: "Closing auction (CAS) started",
    11: "Market orders restricted",
    12: "Closing auction (CAS) ended",
}

_HEADER = struct.Struct("<HHbBBBB")
_U16 = struct.Struct("<H")
_INDEX_BODY = struct.Struct("<IiiiiiQiiidBi21s")
_MINI_BODY = struct.Struct("<IqIqIiiIBI")
_MP_BODY = struct.Struct("<IqqqqqIIIIIqIIIIhiIdiIIIIIBI")
_MP_FIXED_END = 144
_DEPTH_ROW = struct.Struct("<qii")
_DEPTH_ROW_SIZE = 16
_MARKET_STATUS_BODY = struct.Struct("<H5s")
_CAS_CHANGE_BODY = struct.Struct("<IIqq")


@dataclass(frozen=True)
class DepthLevel:
    quantity: int
    price: float
    orders: int

    def to_dict(self) -> dict[str, Any]:
        return {"quantity": self.quantity, "price": self.price, "orders": self.orders}


@dataclass
class MarketPicture:
    type: str = "scrip"
    exchange_segment: str = ""
    instrument_token: str = ""
    trading_symbol: Optional[str] = None
    level: int = 0
    last_traded_price: float = 0.0
    open_price: float = 0.0
    high_price: float = 0.0
    low_price: float = 0.0
    close_price: float = 0.0
    average_trade_price: float = 0.0
    last_trade_time: int = 0
    last_update_time: int = 0
    last_trade_qty: int = 0
    total_buy_quantity: int = 0
    total_sell_quantity: int = 0
    volume_traded_today: int = 0
    open_interest: int = 0
    net_change: float = 0.0
    net_change_percent: float = 0.0
    buy: list[DepthLevel] = field(default_factory=list)
    sell: list[DepthLevel] = field(default_factory=list)


@dataclass
class MiniTouch:
    type: str = "scrip_lite"
    exchange_segment: str = ""
    instrument_token: str = ""
    trading_symbol: Optional[str] = None
    last_traded_price: float = 0.0
    last_trade_time: int = 0
    last_trade_qty: int = 0
    close_price: float = 0.0
    net_change: float = 0.0
    net_change_percent: float = 0.0


@dataclass
class IndexTick:
    type: str = "index"
    exchange_segment: str = ""
    instrument_token: str = ""
    trading_symbol: Optional[str] = None
    name: str = ""
    last_traded_price: float = 0.0
    open_price: float = 0.0
    high_price: float = 0.0
    low_price: float = 0.0
    close_price: float = 0.0
    change: float = 0.0
    net_change_percent: float = 0.0
    last_trade_time: int = 0


@dataclass
class MarketStatus:
    type: str = "market_status"
    exchange_segment: str = ""
    status_code: int = 0
    status: str = ""


FeedMessage = Union[MarketPicture, MiniTouch, IndexTick, MarketStatus]


def split_batch(frame: bytes) -> list[bytes]:
    packets: list[bytes] = []
    offset = 0
    n = len(frame)
    while offset + 2 <= n:
        size = _U16.unpack_from(frame, offset)[0]
        if size < HEADER_SIZE or offset + size > n:
            break
        packets.append(frame[offset : offset + size])
        offset += size
    return packets


def _decode_string(raw: bytes) -> str:
    return raw.split(b"\x00", 1)[0].decode("utf-8", "replace").strip()


def decode_packet(packet: bytes, dividers: dict[int, int]) -> Optional[FeedMessage]:
    if len(packet) < HEADER_SIZE:
        return None
    (
        message_length,
        message_code,
        exchange_id,
        level,
        _auction,
        _seq,
        _bitmask,
    ) = _HEADER.unpack_from(packet, 0)
    exchange = EXCHANGE_ID_TO_NAME.get(exchange_id, str(exchange_id))
    divider = dividers.get(exchange_id) or DEFAULT_DIVIDER

    if message_code in (MSG_MARKET_OPEN, MSG_MARKET_CLOSE):
        code = 1 if message_code == MSG_MARKET_OPEN else 2
        return MarketStatus(
            exchange_segment=exchange,
            status_code=code,
            status=MARKET_STATUS_TEXT[code],
        )
    if message_code == MSG_INDEX:
        return _decode_index(packet, exchange, divider)
    if message_code == MSG_MARKET_STATUS:
        return _decode_market_status(packet, exchange)
    if message_code == MSG_CAS_CHANGE:
        return None  # CAS imbalance not needed for LiveQuote path
    if level == LEVEL_MINI:
        return _decode_mini(packet, exchange, divider)
    if level in (2, LEVEL_TOUCH, LEVEL_DEPTH, LEVEL_FULL_DEPTH):
        return _decode_market_picture(
            packet, exchange, divider, int(level), message_length
        )
    return None


def _decode_index(packet: bytes, exchange: str, divider: int) -> IndexTick:
    (
        token,
        open_price,
        close_price,
        high_price,
        low_price,
        index_value,
        last_trade_time,
        _yh,
        _yl,
        net_chg_percent,
        _mcap,
        _prec,
        _mult,
        name,
    ) = _INDEX_BODY.unpack_from(packet, HEADER_SIZE)
    return IndexTick(
        exchange_segment=exchange,
        instrument_token=str(token),
        name=_decode_string(name),
        last_traded_price=index_value / divider,
        open_price=open_price / divider,
        high_price=high_price / divider,
        low_price=low_price / divider,
        close_price=close_price / divider,
        change=(index_value - close_price) / divider,
        net_change_percent=net_chg_percent / 100.0,
        last_trade_time=int(last_trade_time),
    )


def _decode_market_status(packet: bytes, exchange: str) -> MarketStatus:
    status_code, status_bytes = _MARKET_STATUS_BODY.unpack_from(packet, HEADER_SIZE)
    text = MARKET_STATUS_TEXT.get(status_code)
    if text is None:
        text = _decode_string(status_bytes) or f"Unknown status_code {status_code}"
    return MarketStatus(exchange_segment=exchange, status_code=status_code, status=text)


def _decode_mini(packet: bytes, exchange: str, divider: int) -> MiniTouch:
    (
        token,
        last_trade_time,
        last_traded_price,
        last_trade_qty,
        close_price,
        net_chg_percent,
        net_chg,
        _lot,
        _prec,
        _mult,
    ) = _MINI_BODY.unpack_from(packet, HEADER_SIZE)
    return MiniTouch(
        exchange_segment=exchange,
        instrument_token=str(token),
        last_traded_price=last_traded_price / divider,
        last_trade_time=int(last_trade_time),
        last_trade_qty=int(last_trade_qty),
        close_price=close_price / divider,
        net_change=net_chg / divider,
        net_change_percent=net_chg_percent / 100.0,
    )


def _decode_market_picture(
    packet: bytes,
    exchange: str,
    divider: int,
    level: int,
    message_length: int,
) -> MarketPicture:
    (
        token,
        total_buy_qty,
        total_sell_qty,
        volume_traded_today,
        last_trade_time,
        last_update_time,
        open_price,
        close_price,
        high_price,
        low_price,
        last_traded_price,
        last_trade_qty,
        avg_trade_price,
        _indicative,
        buy_depth_count,
        sell_depth_count,
        _trading_status,
        net_chg_percent,
        open_interest,
        _traded_value,
        net_chg,
        _uc,
        _lc,
        _yh,
        _yl,
        _lot,
        _prec,
        _mult,
    ) = _MP_BODY.unpack_from(packet, HEADER_SIZE)

    if last_update_time < 0:
        last_update_time = 0

    if level == LEVEL_TOUCH:
        buy_n, sell_n = 1, 1
    else:
        buy_n, sell_n = int(buy_depth_count), int(sell_depth_count)

    buy: list[DepthLevel] = []
    sell: list[DepthLevel] = []
    offset = _MP_FIXED_END
    limit = min(message_length, len(packet))
    for i in range(buy_n + sell_n):
        if offset + _DEPTH_ROW_SIZE > limit:
            break
        qty, price, orders = _DEPTH_ROW.unpack_from(packet, offset)
        row = DepthLevel(quantity=int(qty), price=price / divider, orders=int(orders))
        (buy if i < buy_n else sell).append(row)
        offset += _DEPTH_ROW_SIZE

    return MarketPicture(
        exchange_segment=exchange,
        instrument_token=str(token),
        level=level,
        last_traded_price=last_traded_price / divider,
        open_price=open_price / divider,
        high_price=high_price / divider,
        low_price=low_price / divider,
        close_price=close_price / divider,
        average_trade_price=avg_trade_price / divider,
        last_trade_time=int(last_trade_time),
        last_update_time=int(last_update_time),
        last_trade_qty=int(last_trade_qty),
        total_buy_quantity=int(total_buy_qty),
        total_sell_quantity=int(total_sell_qty),
        volume_traded_today=int(volume_traded_today),
        open_interest=int(open_interest),
        net_change=net_chg / divider,
        net_change_percent=net_chg_percent / 100.0,
        buy=buy,
        sell=sell,
    )
