import React from 'react';
import { render, screen } from '@testing-library/react';
import ExpectancyHonestyBanner from './ExpectancyHonestyBanner';

describe('ExpectancyHonestyBanner', () => {
  const honesty = {
    prominent: true,
    insufficient_history_count: 2,
    proxy_count: 1,
    gate_failed_count: 3,
    fail_reasons: ['INSUFFICIENT_5M_HISTORY', 'N<30 (got 4)'],
    label: 'Expectancy honesty — proxy / thin 5m history / gate fails',
    detail: '2 call(s) lack sufficient 5m history',
    boundary: 'Research only — gate pass ≠ proven edge.',
  };

  test('renders counts on intraday and index desks', () => {
    const { rerender } = render(
      <ExpectancyHonestyBanner desk="intraday" honesty={honesty} />,
    );
    expect(screen.getByTestId('expectancy-honesty')).toBeInTheDocument();
    expect(screen.getByText(/Insufficient 5m history: 2/i)).toBeInTheDocument();
    expect(screen.getByText(/Proxy \/ ungated metrics: 1/i)).toBeInTheDocument();
    expect(screen.getByText(/Expectancy\/risk gate failed: 3/i)).toBeInTheDocument();
    expect(screen.getByText(/INSUFFICIENT_5M_HISTORY/)).toBeInTheDocument();
    expect(screen.getByText(/Research only/i)).toBeInTheDocument();

    rerender(<ExpectancyHonestyBanner desk="index" honesty={honesty} />);
    expect(screen.getByTestId('expectancy-honesty')).toHaveAttribute(
      'data-desk',
      'index',
    );
  });

  test('renders on swing; hidden when not prominent or MCX', () => {
    const { rerender } = render(
      <ExpectancyHonestyBanner
        desk="intraday"
        honesty={{ ...honesty, prominent: false }}
      />,
    );
    expect(screen.queryByTestId('expectancy-honesty')).not.toBeInTheDocument();

    rerender(<ExpectancyHonestyBanner desk="swing" honesty={honesty} />);
    expect(screen.getByTestId('expectancy-honesty')).toHaveAttribute(
      'data-desk',
      'swing',
    );

    rerender(<ExpectancyHonestyBanner desk="mcx" honesty={honesty} />);
    expect(screen.queryByTestId('expectancy-honesty')).not.toBeInTheDocument();
  });
});
