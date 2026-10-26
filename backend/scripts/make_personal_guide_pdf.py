#!/usr/bin/env python3
"""Generate Swing Desk personal guide PDF (current stack)."""
from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

OUT = Path(__file__).resolve().parents[2] / "Swing_Desk_Personal_Guide.pdf"

TEXT = """Swing Desk Personal Guide v4.1 (Research only)

USE THIS BUILD
UI http://localhost:3000  |  API http://localhost:8000/docs
.env: KOTAK_CONSUMER_KEY, MAX_INGEST_SYMBOLS=0, ALLOW_DEMO_DATA=false,
AUTH_ENABLED=false, MARKET_DATA_ADAPTER=live (not demo).

DESKS
1) Swing - weekly NSE momentum. BEAR / NIFTY < SMA50 = cash. Radar is watchlist only.
2) Intraday - Yahoo 5m NSE cash BUY/SELL/HOLD. Session-aware. Small size.
3) Index - Nifty + BankNifty multi-timeframe (daily SMA + 5m EMA/VWAP/RSI + BN vs Nifty).
   Strategy id: index_mtf_vwap_v1. Map to F&O yourself. No PCR/option chain here.
4) MCX - commodities tape. Map lots yourself.

CHARTS
Open any stock: candles or line, volume pane, SMA20/SMA50, ranges 1M/3M/6M/1Y.
Price on swing card = Kotak previous close; broker LTP can differ while market is open.

DATA
Force full = all NSE EQ EOD (hours). Refresh = incremental.
Intraday/Index quotes = Yahoo 5m research tape, not a broker stream.

RULES
No order execution. No guaranteed returns. Cash weeks are intentional.
LLM notes are commentary only.
"""


def main() -> None:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_xy(10, 18)
    pdf.cell(190, 10, "Swing Desk - Personal Guide (v4.1)", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    for line in TEXT.splitlines():
        if pdf.get_y() > 270:
            pdf.add_page()
            pdf.set_font("Helvetica", "", 11)
        pdf.multi_cell(190, 6, line)
    pdf.output(str(OUT))
    print("Wrote", OUT)


if __name__ == "__main__":
    main()
