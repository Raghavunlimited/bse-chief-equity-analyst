import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import StrategyEvaluation from './StrategyEvaluation';
import { deskAPI } from '../services/api';

jest.mock('../services/api', () => ({
  deskAPI: {
    getStrategyEvaluation: jest.fn(),
    runStrategyEvaluation: jest.fn(),
  },
}));

const sample = {
  disclaimer: 'Research evidence only — not a guarantee or proof of edge.',
  universe_honesty:
    'The swing walk-forward universe is the current stored list, so delisted names are absent.',
  selects_best: false,
  proven: false,
  strategy_evaluation_version: '5.12.0-strategy-eval',
  test_period: { start: '2025-01-01', end: '2026-10-26' },
  baselines: {
    zero_edge: { expectancy_r: 0, note: 'Reference' },
    nifty_buyhold: { available: false, reason: 'nifty_series_empty' },
  },
  bias_checklist: {
    look_ahead_bias: { status: 'mitigated_in_harness', residual_risk: 'path' },
    multiple_testing: { status: 'risk_acknowledged', selects_best: false },
  },
  evaluations: [
    {
      rule_id: 'elite_momentum',
      evaluable: true,
      available: true,
      evidence: 'evidence_below_gates',
      proven: false,
      best: false,
      sample_size: 12,
      metrics_all: { expectancy_r: 0.1, profit_factor: 1.05 },
      risk: { max_drawdown_pct: -5 },
      out_of_sample: { oos_sample_size: 3, oos_metrics: { expectancy_r: -0.1 } },
      gates: { passes: false, fails: ['N<30'] },
      meta: {
        label: 'India Elite Momentum',
        timeframe: '1d',
        strategy_version: '5.12.0-strategy-eval',
      },
      limitations: ['Not a profit guarantee.'],
    },
    {
      rule_id: 'options_put_call_setup',
      evaluable: false,
      available: false,
      oi_pcr_directional_signal: false,
      note: 'OI/PCR are descriptive only',
      blockers: ['explicit_testable_put_call_rules_missing'],
      proven: false,
      best: false,
    },
  ],
  limitations: ['No strategy is labeled best or proven.'],
};

describe('StrategyEvaluation', () => {
  beforeEach(() => {
    deskAPI.getStrategyEvaluation.mockReset();
    deskAPI.runStrategyEvaluation.mockReset();
  });

  it('shows disclaimer, no-best honesty, metrics, and options non-signal', async () => {
    deskAPI.getStrategyEvaluation.mockResolvedValue({ data: sample });
    render(<StrategyEvaluation />);
    await waitFor(() => {
      expect(screen.getByTestId('eval-list')).toBeInTheDocument();
    });
    expect(screen.getByTestId('eval-disclaimer')).toHaveTextContent(/not a guarantee/i);
    expect(screen.getByTestId('eval-no-best')).toHaveTextContent(/selects_best=false/);
    expect(screen.getByTestId('eval-universe-honesty')).toHaveTextContent(
      /current stored list, so delisted names are absent/i,
    );
    expect(screen.getByTestId('eval-bias')).toBeInTheDocument();
    expect(screen.getByTestId('eval-baselines')).toBeInTheDocument();
    expect(screen.getByText(/India Elite Momentum/)).toBeInTheDocument();
    expect(screen.getByText(/OI\/PCR are descriptive only/)).toBeInTheDocument();
    expect(screen.getByTestId('eval-limitations')).toHaveTextContent(/best or proven/i);
    const rows = screen.getAllByTestId('eval-row');
    expect(rows.length).toBe(2);
  });
});
