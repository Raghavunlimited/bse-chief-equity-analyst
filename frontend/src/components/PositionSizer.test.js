import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import PositionSizer from './PositionSizer';
import { deskAPI } from '../services/api';

jest.mock('../services/api', () => ({
  deskAPI: {
    calculatePositionSize: jest.fn(),
  },
}));

describe('PositionSizer', () => {
  beforeEach(() => {
    deskAPI.calculatePositionSize.mockReset();
  });

  it('shows research disclaimer and formula when size is available', async () => {
    deskAPI.calculatePositionSize.mockResolvedValue({
      data: {
        available: true,
        size: {
          lots: 100,
          units: 100,
          notional: 10000,
          risk_rs: 1000,
        },
        formula: 'risk_budget = capital × (risk_pct/100)',
        formula_detail: 'lots = 100',
        assumptions: ['Research math only'],
        disclaimer: 'Research calculation only — not an order instruction',
        is_order_instruction: false,
        blockers: [],
      },
    });

    render(<PositionSizer />);
    expect(screen.getByTestId('sizing-disclaimer')).toBeInTheDocument();
    fireEvent.change(screen.getByTestId('sizing-entry'), {
      target: { value: '100' },
    });
    fireEvent.change(screen.getByTestId('sizing-stop'), {
      target: { value: '90' },
    });
    fireEvent.click(screen.getByTestId('sizing-submit'));

    await waitFor(() => {
      expect(screen.getByTestId('sizing-available')).toBeInTheDocument();
    });
    expect(screen.getByTestId('sizing-formula')).toHaveTextContent(/risk_budget/i);
    expect(screen.getByText(/Research math only/)).toBeInTheDocument();
  });

  it('explains blockers when unavailable — no fabricated size', async () => {
    deskAPI.calculatePositionSize.mockResolvedValue({
      data: {
        available: false,
        size: null,
        blockers: ['stop_missing', 'contract_mapping_unverified'],
        formula: 'risk_budget = capital × (risk_pct/100)',
        assumptions: ['No fabricated size'],
        disclaimer: 'Research calculation only — not an order instruction',
        is_order_instruction: false,
      },
    });

    render(<PositionSizer />);
    fireEvent.change(screen.getByTestId('sizing-entry'), {
      target: { value: '100' },
    });
    fireEvent.click(screen.getByTestId('sizing-submit'));

    await waitFor(() => {
      expect(screen.getByTestId('sizing-unavailable')).toBeInTheDocument();
    });
    expect(screen.getByText('stop_missing')).toBeInTheDocument();
    expect(screen.queryByTestId('sizing-available')).not.toBeInTheDocument();
  });
});
