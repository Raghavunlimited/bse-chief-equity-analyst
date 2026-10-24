# Swing Desk — QA acceptance checklist

## Feeds
- [ ] No Groww UI chips, buttons, or `/api/feeds/groww`
- [ ] Health exposes Kotak only
- [ ] Test Kotak returns OK with candle count

## Data trust
- [ ] Stats show EOD count + listed NSE EQ (~2500)
- [ ] Provenance chip shows KOTAK (or honest Yahoo/demo)
- [ ] BEAR/cash week explains NIFTY vs SMA clearly
- [ ] Stale banner appears when EOD is old

## Stocks & financials
- [ ] Browse lists full NSE EQ universe with pagination
- [ ] Search finds RELIANCE ahead of similar names
- [ ] Click any stock → PE / ROE / mcap (Screener) or honest error
- [ ] Names with EOD also show chart + RSI

## Performance
- [ ] Force full progress shows concurrent workers (`Kotak ×N`)
- [ ] API stays responsive during ingest (other tabs load)
- [ ] Stock modal loads in a few seconds for cached financials

## Regression
```bash
cd backend && source venv/bin/activate && python test_world_class.py
```
