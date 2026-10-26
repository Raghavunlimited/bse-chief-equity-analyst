import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import IntradayDesk from './IntradayDesk';
import { deskAPI } from '../services/api';

jest.mock('../services/api', () => ({
  deskAPI: {
    getIntradayDesk: jest.fn(),
  },
}));

describe('IntradayDesk expectancy honesty', () => {
  afterEach(() => jest.clearAllMocks());

  test('surfaces board expectancy_honesty banner without inventing signals', async () => {
    deskAPI.getIntradayDesk.mockResolvedValue({
      data: {
        desk: 'intraday',
        signals: [
          {
            symbol: 'INFY',
            side: 'HOLD',
            badge: 'HOLD',
            expectancy: {
              insufficient_history: true,
              status_label: 'insufficient_5m_history',
              gates: {
                passed: false,
                fail_reasons: ['INSUFFICIENT_5M_HISTORY'],
              },
            },
          },
        ],
        buy_count: 0,
        sell_count: 0,
        expectancy_honesty: {
          prominent: true,
          insufficient_history_count: 1,
          proxy_count: 0,
          gate_failed_count: 1,
          fail_reasons: ['INSUFFICIENT_5M_HISTORY'],
          label: 'Expectancy honesty — proxy / thin 5m history / gate fails',
          detail: '1 call(s) lack sufficient 5m history — STRONG / edge blocked',
          boundary: 'Research only — gate pass ≠ proven edge.',
        },
        signal_availability: {
          code: 'gate_blocked',
          label: 'No actionable signal — insufficient history or expectancy/risk gates failed',
        },
      },
    });

    render(<IntradayDesk />);
    await waitFor(() => {
      expect(screen.getByTestId('expectancy-honesty')).toBeInTheDocument();
    });
    expect(screen.getByText(/Insufficient 5m history: 1/i)).toBeInTheDocument();
    expect(screen.getByText('INFY')).toBeInTheDocument();
  });
});
