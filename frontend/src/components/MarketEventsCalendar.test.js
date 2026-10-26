import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import MarketEventsCalendar from './MarketEventsCalendar';
import { deskAPI } from '../services/api';

jest.mock('../services/api', () => ({
  deskAPI: {
    getMarketEvents: jest.fn(),
  },
}));

const sample = {
  disclaimer: 'Identifiable-source calendar only — not a live scrape.',
  licensing: { note: 'No commercial calendar license.' },
  feeds_summary: {
    any_stale: true,
    stale_not_current: true,
    all_unavailable: false,
    any_fresh: false,
    any_presented_as_current: false,
  },
  feeds: [
    {
      source_id: 'nse_holidays_snapshot',
      source: {
        id: 'nse_holidays_snapshot',
        label: 'NSE cash holiday snapshot',
        as_of: '2026-01-15',
        last_updated: '2026-01-15T00:00:00Z',
        license: 'operator snapshot',
        is_current: false,
        presented_as_current: false,
      },
      feed: {
        status: 'stale',
        stale: true,
        is_current: false,
        presented_as_current: false,
        reason: 'STALE — not a current calendar',
        last_updated: '2026-01-15T00:00:00Z',
      },
    },
  ],
  events: [
    {
      id: 'ev1',
      title: 'Christmas',
      status: 'scheduled',
      content_kind: 'scheduled_fact',
      content_kind_label: 'Scheduled fact',
      event_time_utc: '2026-12-24T18:30:00Z',
      event_time_local: '2026-12-25T00:00:00+05:30',
      timezone: 'Asia/Kolkata',
      feed_status: 'stale',
      is_current: false,
      presented_as_current: false,
      source: {
        id: 'nse_holidays_snapshot',
        label: 'NSE cash holiday snapshot',
        last_updated: '2026-01-15T00:00:00Z',
        license: 'operator snapshot',
      },
      model_commentary: null,
      outcome: null,
      changed: false,
    },
  ],
};

describe('MarketEventsCalendar', () => {
  beforeEach(() => {
    deskAPI.getMarketEvents.mockReset();
  });

  it('shows disclaimer, source, times, feed stale, and no model commentary', async () => {
    deskAPI.getMarketEvents.mockResolvedValue({ data: sample });
    render(<MarketEventsCalendar />);

    await waitFor(() => {
      expect(screen.getByTestId('event-row')).toBeInTheDocument();
    });
    expect(screen.getByTestId('events-disclaimer')).toHaveTextContent(
      /Identifiable-source/i,
    );
    expect(screen.getByTestId('events-licensing')).toHaveTextContent(
      /commercial calendar license/i,
    );
    expect(screen.getByTestId('events-stale-banner')).toBeInTheDocument();
    expect(screen.getByTestId('events-stale-banner')).toHaveTextContent(
      /not a current/i,
    );
    expect(screen.getByText('Christmas')).toBeInTheDocument();
    expect(screen.getByText(/Asia\/Kolkata/)).toBeInTheDocument();
    expect(screen.getAllByText(/NSE cash holiday snapshot/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByTestId('feed-status-stale')).toHaveTextContent(
      /STALE — not current/i,
    );
    expect(screen.getByTestId('feed-not-current')).toBeInTheDocument();
    expect(
      screen.getAllByText(/No model-generated commentary/).length,
    ).toBeGreaterThanOrEqual(1);
    expect(screen.queryByTestId('event-model-commentary')).not.toBeInTheDocument();
    const row = screen.getByTestId('event-row');
    expect(row).toHaveAttribute('data-content-kind', 'scheduled_fact');
    expect(row).toHaveAttribute('data-feed-status', 'stale');
    expect(row).toHaveAttribute('data-presented-as-current', 'false');
    expect(screen.getByTestId('event-not-current')).toHaveTextContent(
      /STALE — not current/i,
    );
  });

  it('surfaces all-unavailable honesty', async () => {
    deskAPI.getMarketEvents.mockResolvedValue({
      data: {
        ...sample,
        events: [],
        feeds_summary: {
          any_stale: false,
          all_unavailable: true,
          any_fresh: false,
        },
        feeds: [
          {
            source_id: 'x',
            source: { label: 'X' },
            feed: { status: 'unavailable', reason: 'missing' },
          },
        ],
      },
    });
    render(<MarketEventsCalendar />);
    await waitFor(() => {
      expect(screen.getByTestId('events-all-unavailable')).toBeInTheDocument();
    });
  });
});
