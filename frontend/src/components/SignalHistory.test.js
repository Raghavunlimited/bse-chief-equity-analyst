import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import SignalHistory from './SignalHistory';
import { deskAPI } from '../services/api';

jest.mock('../services/api', () => ({
  deskAPI: {
    platformSignals: jest.fn(),
  },
}));

describe('SignalHistory', () => {
  afterEach(() => {
    jest.clearAllMocks();
  });

  test('empty ledger with demo filter does not suggest seed_platform', async () => {
    deskAPI.platformSignals.mockResolvedValue({
      data: {
        signals: [],
        count: 0,
        filtered_demo_rows: 4,
        ledger_availability: {
          code: 'ledger_demo_filtered',
          label: 'Legacy demo ledger rows are hidden',
          detail:
            '4 legacy demo row(s) hidden. Admin publish with data_mode live/delayed/eod. seed_platform is retired.',
          boundary: 'Research only — not an order instruction and not a return guarantee.',
        },
      },
    });
    render(<SignalHistory category="swing" />);
    await waitFor(() => {
      expect(screen.getByText(/Legacy demo ledger rows are hidden/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/run seed_platform/i)).not.toBeInTheDocument();
    expect(screen.getAllByText(/Research only/i).length).toBeGreaterThanOrEqual(1);
  });

  test('empty ledger with no demos shows ledger_empty honesty', async () => {
    deskAPI.platformSignals.mockResolvedValue({
      data: {
        signals: [],
        count: 0,
        filtered_demo_rows: 0,
        ledger_availability: {
          code: 'ledger_empty',
          label: 'No published ledger signals for this desk',
          detail: 'Ask an admin to publish. seed_platform is retired.',
        },
      },
    });
    render(<SignalHistory category="intraday" />);
    await waitFor(() => {
      expect(
        screen.getByText(/No published ledger signals for this desk/i),
      ).toBeInTheDocument();
    });
    expect(screen.queryByText(/run seed_platform/i)).not.toBeInTheDocument();
  });

  test('published row shows desk strategy source status and gate', async () => {
    deskAPI.platformSignals.mockResolvedValue({
      data: {
        signals: [
          {
            id: '1',
            symbol: 'RELIANCE',
            instrument: 'RELIANCE',
            desk: 'swing',
            strategy: 'weekly_swing',
            direction: 'BUY',
            status: 'published',
            revision: 1,
            data_mode: 'delayed',
            data_status: 'DELAYED',
            data_source: 'admin_publish',
            data_timestamp: '2026-10-26T10:00:00',
            created_at: '2026-10-26T10:00:00',
            rationale: 'Research note',
            gate_result: {
              code: 'ledger_manual',
              label: 'Admin-published research note (not auto-gated)',
            },
          },
        ],
        count: 1,
        filtered_demo_rows: 0,
        ledger_availability: {
          code: 'ledger_has_published',
          label: 'Published ledger signal(s)',
          detail: '1 published non-demo ledger row(s).',
        },
      },
    });
    render(<SignalHistory category="swing" />);
    await waitFor(() => {
      expect(screen.getByText('RELIANCE')).toBeInTheDocument();
    });
    expect(screen.getByText('BUY')).toBeInTheDocument();
    expect(screen.getByText('weekly_swing')).toBeInTheDocument();
    expect(
      screen.getAllByText(/Admin-published research note/i).length,
    ).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('admin_publish').length).toBeGreaterThanOrEqual(1);
  });
});
