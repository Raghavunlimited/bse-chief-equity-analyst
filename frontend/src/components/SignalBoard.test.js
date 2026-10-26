import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import SignalBoard, { normalizeSignal } from './SignalBoard';

describe('SignalBoard', () => {
  test('normalizeSignal maps LONG→BUY and SHORT→SELL', () => {
    expect(normalizeSignal({ symbol: 'A', side: 'LONG', score: 70 }).side).toBe(
      'BUY',
    );
    expect(normalizeSignal({ symbol: 'B', side: 'SHORT', score: 20 }).side).toBe(
      'SELL',
    );
    expect(normalizeSignal({ symbol: 'C', side: 'FLAT' }).side).toBe('HOLD');
  });

  test('renders BUY badge and fires onAnalyze', () => {
    const onAnalyze = jest.fn();
    render(
      <SignalBoard
        signals={[
          {
            id: '1',
            symbol: 'RELIANCE',
            side: 'BUY',
            confidence: 72,
            thesis: 'Test thesis',
            entry: 100,
            stop: 95,
            targets: { t1: 105 },
          },
        ]}
        onAnalyze={onAnalyze}
      />,
    );
    expect(screen.getByText('BUY')).toBeInTheDocument();
    expect(screen.getByText('RELIANCE')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /analyze with llm/i }));
    expect(onAnalyze).toHaveBeenCalledTimes(1);
  });

  test('renders STRONG BUY and real expectancy metrics on card', () => {
    render(
      <SignalBoard
        signals={[
          {
            id: '2',
            symbol: 'INFY',
            side: 'BUY',
            badge: 'STRONG_BUY',
            confidence: 80,
            thesis: 'Research thesis',
            entry: 1500,
            stop: 1450,
            targets: { t1: 1600 },
            expectancy: {
              sample_size: 42,
              win_rate_pct: 58.5,
              expectancy_r: 0.31,
              profit_factor: 1.45,
              active_regime: 'BULL_TREND',
              rule_id: 'elite_momentum',
              gates: { passed: true },
            },
          },
        ]}
      />,
    );
    expect(screen.getByText('STRONG BUY')).toBeInTheDocument();
    expect(screen.getByText('STRONG BUY')).not.toHaveClass('sig-badge--held');
    expect(screen.getByText('58.5%')).toBeInTheDocument();
    expect(screen.getByText('0.31R')).toBeInTheDocument();
    expect(screen.getByText('1.45')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
  });

  test('normalizeSignal surfaces badge and expectancy', () => {
    const n = normalizeSignal({
      symbol: 'TCS',
      side: 'BUY',
      badge: 'STRONG_BUY',
      expectancy: { sample_size: 30, win_rate_pct: 51 },
    });
    expect(n.badge).toBe('STRONG_BUY');
    expect(n.expectancy.sample_size).toBe(30);
  });

  test('renders feed meta for Yahoo FALLBACK and last observation', () => {
    render(
      <SignalBoard
        signals={[
          {
            id: '3',
            symbol: 'SBIN',
            side: 'HOLD',
            market_data_state: 'FALLBACK',
            source: 'yahoo_chart',
            timeframe: '5m',
            quote_age_sec: 2,
            is_current_live: false,
            thesis: 'research only',
          },
        ]}
      />,
    );
    expect(screen.getByText('YAHOO FALLBACK')).toBeInTheDocument();
    expect(screen.getByText('yahoo_chart')).toBeInTheDocument();
  });

  test('stale last observation is not labeled broker live', () => {
    const n = normalizeSignal({
      symbol: 'INFY',
      side: 'HOLD',
      market_data_state: 'STALE',
      is_current_live: false,
      is_last_observation: true,
      signal_generation: 'halted',
      quote_source: 'yahoo_chart',
      quote_age_sec: 12,
    });
    expect(n.isCurrentLive).toBe(false);
    expect(n.isLastObs).toBe(true);
    expect(n.marketDataState).toBe('STALE');
  });

  test('shows availability banner for no_qualifying vs data_blocked', () => {
    const { rerender } = render(
      <SignalBoard
        signals={[]}
        availability={{
          code: 'no_qualifying',
          label: 'No qualifying signal — strategy conditions not met',
          detail: 'Cash week',
        }}
      />,
    );
    expect(
      screen.getByText(/No qualifying signal — strategy conditions not met/i),
    ).toBeInTheDocument();
    rerender(
      <SignalBoard
        signals={[]}
        availability={{
          code: 'data_blocked',
          label: 'Signal evaluation blocked — data stale or unavailable',
          detail: 'EOD stale',
        }}
      />,
    );
    expect(
      screen.getByText(/Signal evaluation blocked — data stale or unavailable/i),
    ).toBeInTheDocument();
  });

  test('card shows desk strategy data status and gate result', () => {
    render(
      <SignalBoard
        desk="intraday"
        signals={[
          {
            id: '9',
            symbol: 'SBIN',
            desk: 'intraday',
            strategy: 'intraday_desk',
            side: 'HOLD',
            data_status: 'STALE',
            data_source: 'yahoo_chart',
            data_timestamp: '2026-10-26T12:00:00Z',
            gate_result: {
              code: 'insufficient_history',
              label: 'Insufficient history — STRONG / edge blocked',
              insufficient_history: true,
            },
            expectancy: {
              insufficient_history: true,
              status_label: 'insufficient_5m_history',
              gates: { passed: false, fail_reasons: ['INSUFFICIENT_5M_HISTORY'] },
            },
            thesis: 'halted observation',
          },
        ]}
      />,
    );
    expect(screen.getByText('SBIN')).toBeInTheDocument();
    const metaBits = ['intraday', 'intraday_desk', 'STALE'];
    metaBits.forEach((bit) => {
      expect(document.body.textContent).toContain(bit);
    });
    expect(
      screen.getByText(/Insufficient history — STRONG \/ edge blocked/i),
    ).toBeInTheDocument();
  });

  test('normalizeSignal prefers data_status and gate_result', () => {
    const n = normalizeSignal({
      symbol: 'NIFTY',
      desk: 'index',
      strategy: 'index_desk',
      side: 'HOLD',
      data_status: 'FALLBACK',
      data_source: 'yahoo_5m',
      gate_result: {
        code: 'gate_failed',
        label: 'Expectancy/risk gate failed',
        passed: false,
      },
    });
    expect(n.marketDataState).toBe('FALLBACK');
    expect(n.quoteSource).toBe('yahoo_5m');
    expect(n.gateResult.code).toBe('gate_failed');
    expect(n.desk).toBe('index');
    expect(n.strategy).toBe('index_desk');
  });

  test('STRONG is held when the gate fails, history is thin, or the result is a proxy', () => {
    const { rerender } = render(
      <SignalBoard
        signals={[
          {
            id: 'g',
            symbol: 'TCS',
            side: 'BUY',
            badge: 'STRONG_BUY',
            tags: ['EDGE_PROVEN', 'proven', 'GATE_PASS_RESEARCH'],
            expectancy: {
              gates: { passed: false, fail_reasons: ['N<30 (got 4)'] },
              sample_size: 4,
            },
          },
        ]}
      />,
    );
    const blocked = screen.getByText('STRONG BUY');
    expect(blocked).toHaveClass('sig-badge--held');
    expect(blocked).not.toHaveClass('sig-badge--strong-buy');
    expect(blocked.closest('article')).not.toHaveClass('sig--strong-buy');
    expect(screen.getByText('Gate failed — STRONG is held')).toBeInTheDocument();
    expect(screen.getByText('N<30 (got 4)')).toBeInTheDocument();
    expect(screen.queryByText('EDGE_PROVEN')).not.toBeInTheDocument();
    expect(screen.queryByText('proven')).not.toBeInTheDocument();
    expect(screen.getByText('GATE_PASS_RESEARCH')).toBeInTheDocument();

    rerender(
      <SignalBoard
        signals={[
          {
            id: 'h',
            symbol: 'TCS',
            side: 'BUY',
            badge: 'STRONG_BUY',
            expectancy: {
              insufficient_history: true,
              gates: { passed: false, fail_reasons: ['INSUFFICIENT_5M_HISTORY'] },
            },
          },
        ]}
      />,
    );
    expect(screen.getByText(/insufficient — STRONG blocked/i)).toBeInTheDocument();
    expect(screen.getByText('Thin history — STRONG is held')).toBeInTheDocument();
    expect(screen.getByText('STRONG BUY')).toHaveClass('sig-badge--held');

    rerender(
      <SignalBoard
        signals={[
          {
            id: 'p',
            symbol: 'TCS',
            side: 'SELL',
            badge: 'STRONG_SELL',
            expectancy: { proxy: true, gates: { passed: true } },
          },
        ]}
      />,
    );
    expect(screen.getByText(/ungated — STRONG blocked/i)).toBeInTheDocument();
    expect(screen.getByText('Proxy data — STRONG is held')).toBeInTheDocument();
    expect(screen.getByText('STRONG SELL')).toHaveClass('sig-badge--held');
    expect(screen.getByText('STRONG SELL').closest('article')).not.toHaveClass(
      'sig--strong-sell',
    );
  });
});
