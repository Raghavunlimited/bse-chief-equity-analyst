# Swing Desk — Company ops (v3.3)

## Org that shipped this release

| Seat | Focus |
|------|--------|
| CEO (you) | Product intent: professional BUY/SELL/HOLD desks + BYO LLM |
| CTO | Production readiness, security, go-live blockers → `CTO_READINESS.md` |
| Principal Architect | System design + API contracts → `ARCHITECTURE.md`, `API_CONTRACT.md` |
| Program Manager | PRD + roadmap → `PRD.md`, `ROADMAP.md` |
| Markets Researcher | Playbooks + LLM guardrails → `RESEARCH_SIGNAL_PLAYBOOK.md` |
| Signal Consultants | Grading voice + rules → `CONSULTANT_VOICE.md`, `signals/consultant_rules.py` |
| Staff SWE (BE) | `/api/consultant/*` signal pipeline |
| Staff SWE (FE) | Multi-desk terminal, SignalBoard, Settings / LLM |
| Senior SWE | BYO LLM `/api/analyze`, enrichment (financials; honest OI gap) |
| EM + QA | Acceptance + automation → `ACCEPTANCE.md`, `test_*.py` |

## Product surface (what clients see)

1. **Swing** — weekly consultant calls (BUY only when regime allows; else HOLD/cash)
2. **Intraday** — daily BUY/SELL/HOLD from live 5m tape (auto-refresh)
3. **MCX** — commodity majors + USDINR (map to MCX lots yourself)
4. **Settings** — optional OpenAI/Anthropic key in browser for Analyze with LLM
5. **Journal / planner** — process tracking (not broker fills)

## Honesty clause (non-negotiable)

No desk guarantees returns. Cash weeks and HOLD calls are features.
OI is not fabricated — vendor integration is a roadmap item.

## Runbook

```bash
./start.sh
# http://localhost:3000
# http://localhost:8000/docs
cd backend && source venv/bin/activate
python test_api_suite.py
python test_analyze_validation.py
```
