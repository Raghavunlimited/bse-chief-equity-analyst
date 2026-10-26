import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import ChartWorkstation from './ChartWorkstation';

jest.mock('lightweight-charts', () => ({
  CrosshairMode: { Normal: 0 },
  createChart: () => {
    const scale = {
      fitContent: jest.fn(),
      subscribeVisibleLogicalRangeChange: jest.fn(),
      getVisibleLogicalRange: () => null,
      setVisibleLogicalRange: jest.fn(),
      visible: false,
    };
    const series = {
      setData: jest.fn(),
      update: jest.fn(),
      createPriceLine: jest.fn(() => ({})),
      removePriceLine: jest.fn(),
    };
    return {
      addCandlestickSeries: () => series,
      addLineSeries: () => series,
      addHistogramSeries: () => series,
      addAreaSeries: () => series,
      timeScale: () => scale,
      applyOptions: jest.fn(),
      remove: jest.fn(),
    };
  },
}));

jest.mock('../services/api', () => ({
  deskAPI: {
    getChart: jest.fn(),
    getChartLive: jest.fn(),
  },
}));

const { deskAPI } = require('../services/api');

describe('ChartWorkstation', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  test('shows loading then source/status from API', async () => {
    deskAPI.getChart.mockResolvedValue({
      data: {
        has_data: true,
        status: 'ok',
        source: 'kotak_eod_db',
        price_kind: 'eod_close',
        ltp: 2500,
        bars: [
          { time: '2026-10-01', open: 1, high: 2, low: 0.5, close: 1.5, volume: 10 },
          { time: '2026-10-02', open: 1.5, high: 2.5, low: 1, close: 2, volume: 12 },
        ],
        volume: [],
        ema_ribbon: {},
        rsi: [],
        macd: { macd: [], signal: [], histogram: [] },
        oi: [],
        walls: null,
        freshness: { status: 'ok', label: 'EOD', age_sec: 100 },
        range: { returned_bars: 2 },
        missing_bars_skipped: 0,
        timezone: { display_timezone: 'Asia/Kolkata', note: 'IST' },
        optional_features: {
          walls: { available: false, reason: 'inactive' },
          oi: { available: false, reason: 'no_oi' },
          pcr: { available: false },
          depth_l2: { available: false },
        },
      },
    });
    deskAPI.getChartLive.mockResolvedValue({
      data: { ltp: 2500, bar: null, has_data: true, status: 'ok' },
    });

    render(<ChartWorkstation symbol="RELIANCE" defaultInterval="1d" />);
    expect(screen.getByTestId('chart-loading')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId('chart-source')).toHaveTextContent('kotak_eod_db');
    });
    expect(screen.getByTestId('walls-unavailable')).toBeInTheDocument();
    expect(screen.getByTestId('chart-status')).toBeInTheDocument();
    expect(screen.getByText(/TZ Asia\/Kolkata/)).toBeInTheDocument();
  });

  test('shows error state when API has no data', async () => {
    deskAPI.getChart.mockResolvedValue({
      data: {
        has_data: false,
        status: 'unavailable',
        message: 'No candles for XYZ',
        bars: [],
        optional_features: {
          walls: { available: false },
          oi: { available: false },
        },
        freshness: { status: 'unavailable', label: 'UNAVAILABLE' },
      },
    });
    deskAPI.getChartLive.mockResolvedValue({ data: { has_data: false } });

    render(<ChartWorkstation symbol="XYZ" />);
    await waitFor(() => {
      expect(screen.getByTestId('chart-error')).toHaveTextContent(/No candles/);
    });
  });
});
