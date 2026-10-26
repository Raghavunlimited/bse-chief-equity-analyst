import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import TradeLedger from './TradeLedger';

jest.mock('../services/api', () => ({
  deskAPI: {
    getLedgerSummary: jest.fn(),
    postLedgerMovement: jest.fn(),
    openLedgerTrade: jest.fn(),
    exitLedgerTrade: jest.fn(),
  },
}));

const { deskAPI } = require('../services/api');

describe('TradeLedger', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('shows disclaimer and separates unrealized from book', async () => {
    deskAPI.getLedgerSummary.mockResolvedValue({
      data: {
        disclaimer: 'User-entered research journal only — not verified broker fills.',
        source_label: 'user_entered_not_broker_fill',
        capital: {
          starting_capital: 100000,
          deposits: 0,
          withdrawals: 0,
          realized_pnl: 100,
          costs_fees_total: 10,
          book_equity: 100100,
          formula: 'book = start + dep - wd + realized',
        },
        estimated_unrealized: {
          available: false,
          total: null,
          label: 'estimated_unrealized_pnl_separate_from_book',
        },
        estimated_equity_mark: { available: false, value: null },
        open_positions: [],
        closed_positions: [],
      },
    });

    render(<TradeLedger />);
    await waitFor(() => {
      expect(screen.getByTestId('ledger-capital')).toHaveTextContent('Book equity');
    });
    expect(screen.getByTestId('ledger-disclaimer')).toHaveTextContent(
      /not verified broker fills/i,
    );
    expect(screen.getAllByText('unavailable').length).toBeGreaterThanOrEqual(1);
  });
});
