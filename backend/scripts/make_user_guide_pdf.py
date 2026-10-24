#!/usr/bin/env python3
"""Generate Swing Desk user guide PDF (Helvetica / ASCII)."""
from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

OUT = Path(__file__).resolve().parents[2] / "Swing_Desk_User_Guide.pdf"

TEXT = """Swing Desk User Guide v3.4 (Research only - not investment advice)

1. START
Run ./start.sh and open http://localhost:3000
API docs: http://localhost:8000/docs (disable with ENABLE_API_DOCS=false)
Kotak Neo consumer key in backend/.env then Refresh / Force full.

2. DESK TABS
Swing - weekly NSE consultant BUY/HOLD (cash in BEAR), planner, journal, radar
Intraday - live BUY/SELL/HOLD board (~15s refresh) with VWAP / ORB / momentum tags
MCX - Gold, Silver, Crude, NatGas, Copper + USDINR (map to MCX lots yourself)

3. CONSULTANT CALLS
Each card: side, confidence, entry/stop/T1, thesis, tags.
Open a symbol for chart + financials + signal context (volume; OI honest-empty).
Log trade -> week tracker for invested capital and P&L.

4. LLM SETTINGS (why you see more than Haiku)
Click Settings. Choose a model, not just a provider:
  Anthropic: Claude Opus 4 (strongest), Sonnet 4, 3.5 Haiku, Claude 3 Opus
  OpenAI: GPT-4o, GPT-4o mini, o3-mini
Paste your own API key (sk-ant-... or sk-...). Stored only in this browser.
Click Analyze with LLM on any call. Key is sent only for that request.

5. HEALTH
GET /api/health = process up
GET /api/health/ready = fresh EOD (503 if stale/demo blocked)

6. HONEST RULES
No system guarantees weekly % returns. BEAR cash weeks are intentional.
Commodities are leveraged. Size risk yourself.

7. TROUBLESHOOTING
Only Haiku showing? Refresh the page after this update; reopen Settings.
LLM 401: wrong key for that provider (Anthropic vs OpenAI).
Empty swing BUYs: regime BEAR - use Intraday/MCX or wait for NIFTY.
"""


def main() -> None:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_xy(10, 20)
    pdf.cell(190, 10, "Swing Desk - How to Use (v3.4)", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 11)
    for line in TEXT.splitlines():
        if pdf.get_y() > 270:
            pdf.add_page()
            pdf.set_font("Helvetica", "", 11)
        pdf.set_x(10)
        pdf.cell(0, 6, line[:115], new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(OUT))
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
