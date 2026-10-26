import React from 'react';
import { render, screen } from '@testing-library/react';
import OiComparisonChart from './OiComparisonChart';

describe('OiComparisonChart', () => {
  test('shows unavailable state without inventing bars', () => {
    render(
      <OiComparisonChart
        viz={{
          available: false,
          status: 'unavailable',
          blocker: 'Requires Kotak activate',
          provider: 'kotak_neo_ws',
          provider_e2e_verified_in_ci: false,
          signal_disclaimer: 'OI not a trade signal',
          expiries_oi_comparison: [
            { expiry: '2026-11-03', oi_available: false, reason: 'chain_not_activated_for_expiry' },
          ],
        }}
      />,
    );
    expect(screen.getByTestId('oi-viz-unavailable')).toBeInTheDocument();
    expect(screen.getByText(/Requires Kotak activate/)).toBeInTheDocument();
    expect(screen.getByText(/OI unavailable/)).toBeInTheDocument();
    expect(screen.getByTestId('oi-viz-disclaimer')).toHaveTextContent(/not a trade signal/i);
  });

  test('renders call/put OI rows and marks missing legs', () => {
    render(
      <OiComparisonChart
        viz={{
          available: true,
          status: 'ok',
          underlying: 'NIFTY',
          active_expiry: '2026-11-03',
          source: 'kotak_neo_ws',
          freshness: { status: 'ok', label: 'FRESH', max_age_sec: 1 },
          underlying_price: { available: true, value: 24500 },
          totals: {
            call_oi: 1000,
            put_oi: 2000,
            call_oi_available: true,
            put_oi_available: true,
            pcr: 2,
            pcr_note: 'descriptive',
          },
          series: [
            {
              strike: 24400,
              atm: false,
              call: { oi: { available: true, value: 400 } },
              put: { oi: { available: true, value: 500 } },
            },
            {
              strike: 24500,
              atm: true,
              call: { oi: { available: false, reason: 'no_live_quote' } },
              put: { oi: { available: true, value: 900 } },
            },
          ],
          call_oi_by_strike: [
            { strike: 24400, oi: 400 },
            { strike: 24500, oi: null },
          ],
          put_oi_by_strike: [
            { strike: 24400, oi: 500 },
            { strike: 24500, oi: 900 },
          ],
          expiries_oi_comparison: [
            {
              expiry: '2026-11-03',
              active: true,
              oi_available: true,
              call_oi_total: 1000,
              put_oi_total: 2000,
            },
            {
              expiry: '2026-11-10',
              active: false,
              oi_available: false,
              reason: 'chain_not_activated_for_expiry',
              call_oi_total: null,
              put_oi_total: null,
            },
          ],
          signal_disclaimer: 'descriptive only',
          field_semantics: {
            iv: 'model_derived_from_ltp_not_exchange_iv',
            oi_change: 'session_delta_vs_baseline_or_prev_day_oi',
          },
        }}
      />,
    );
    expect(screen.getByTestId('oi-viz')).toBeInTheDocument();
    expect(screen.getByTestId('oi-viz-freshness')).toHaveTextContent('FRESH');
    expect(screen.getByText('n/a')).toBeInTheDocument();
    expect(screen.getByText(/chain_not_activated_for_expiry/)).toBeInTheDocument();
  });
});
