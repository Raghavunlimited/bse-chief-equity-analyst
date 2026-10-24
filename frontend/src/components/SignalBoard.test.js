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
});
