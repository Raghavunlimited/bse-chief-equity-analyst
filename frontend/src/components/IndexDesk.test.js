import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import IndexDesk from './IndexDesk';
import { deskAPI } from '../services/api';

jest.mock('../services/api', () => ({
  deskAPI: {
    getIndexDesk: jest.fn(),
  },
}));

describe('IndexDesk expectancy honesty', () => {
  afterEach(() => jest.clearAllMocks());

  test('surfaces proxy and gate-fail honesty on index board', async () => {
    deskAPI.getIndexDesk.mockResolvedValue({
      data: {
        desk: 'index',
        strategy: 'index_mtf_vwap_v1',
        signals: [
          {
            symbol: 'NIFTY',
            side: 'HOLD',
            badge: 'HOLD',
            expectancy: {
              proxy: true,
              status_label: 'proxy_disabled',
              gates: { passed: false, fail_reasons: ['PROXY_OR_DAILY_INTERVAL'] },
            },
          },
        ],
        buy_count: 0,
        sell_count: 0,
        expectancy_honesty: {
          prominent: true,
          insufficient_history_count: 0,
          proxy_count: 1,
          gate_failed_count: 1,
          fail_reasons: ['PROXY_OR_DAILY_INTERVAL'],
          label: 'Expectancy honesty — proxy / thin 5m history / gate fails',
          detail: '1 call(s) use proxy or ungated metrics — STRONG blocked',
        },
        signal_availability: { code: 'gate_blocked', label: '…' },
      },
    });

    render(<IndexDesk />);
    await waitFor(() => {
      expect(screen.getByTestId('expectancy-honesty')).toBeInTheDocument();
    });
    expect(screen.getByTestId('expectancy-honesty')).toHaveAttribute(
      'data-desk',
      'index',
    );
    expect(screen.getByText(/Proxy \/ ungated metrics: 1/i)).toBeInTheDocument();
  });
});
