import React, { useCallback, useEffect, useState } from 'react';
import { deskAPI } from '../services/api';

function feedTone(status) {
  if (status === 'fresh') return 'is-up';
  if (status === 'stale') return 'is-down';
  return 'muted';
}

export default function MarketEventsCalendar() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await deskAPI.getMarketEvents({ include_fo: true });
      setData(res.data);
    } catch (err) {
      setData(null);
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const events = data?.events || [];
  const feeds = data?.feeds || [];
  const summary = data?.feeds_summary || {};

  return (
    <section
      className="section market-events"
      id="section-market-events"
      data-testid="market-events"
    >
      <div className="section__head">
        <div>
          <h3>Market events</h3>
          <p className="section-sub">
            Identifiable sources only (NSE holiday snapshot, operator file, optional
            Kotak F&amp;O expiries). No invented dates, forecasts, outcomes, or impact.
          </p>
        </div>
        <button type="button" className="btn ghost" onClick={load} disabled={loading}>
          Refresh
        </button>
      </div>

      <p className="banner warn" role="note" data-testid="events-disclaimer">
        {data?.disclaimer ||
          'Identifiable-source calendar only — not a live economic calendar scrape.'}
      </p>

      <p className="muted" data-testid="events-licensing">
        {data?.licensing?.note ||
          'No commercial economic-calendar license claimed — identifiable snapshots only.'}
      </p>

      {error && (
        <p className="error-text" role="alert">
          {String(error)}
        </p>
      )}
      {loading && !data && <p className="muted">Loading events…</p>}

      {data && (
        <div className="market-events__feeds" data-testid="events-feeds">
          {feeds.map((f) => {
            const st = f.feed?.status || 'unavailable';
            const src = f.source || {};
            return (
              <div key={f.source_id || src.id} className="market-events__feed">
                <strong>{src.label || f.source_id}</strong>
                <span className={feedTone(st)} data-testid={`feed-status-${st}`}>
                  {st === 'stale'
                    ? 'STALE — not current'
                    : st === 'fresh'
                      ? 'fresh'
                      : st}
                </span>
                <span className="muted">
                  as_of {src.as_of || f.feed?.as_of || '—'} · updated{' '}
                  {f.feed?.last_updated || src.last_updated || '—'}
                </span>
                {f.feed?.is_current === false ||
                f.feed?.presented_as_current === false ||
                f.feed?.stale ||
                st === 'unavailable' ? (
                  <em className="muted" data-testid="feed-not-current">
                    {f.feed?.reason || 'Not presented as a current calendar.'}
                  </em>
                ) : null}
              </div>
            );
          })}
          {summary.all_unavailable ? (
            <p className="banner warn" data-testid="events-all-unavailable">
              All event feeds unavailable — nothing invented to fill the gap.
            </p>
          ) : null}
          {summary.any_stale || summary.stale_not_current ? (
            <p className="banner warn" data-testid="events-stale-banner">
              STALE calendar data — not a current NSE / operator feed. Dates below
              remain listed for research but must not be treated as a verified current
              circular. To refresh: verify the latest NSE cash-market holiday circular,
              then update <code>backend/app/data/nse_holidays.json</code> (and optional{' '}
              <code>market_events.json</code>) including a new operator-verified{' '}
              <code>as_of</code>. Do not bump <code>as_of</code> without that check —
              stale stays labeled stale on purpose.
            </p>
          ) : null}
        </div>
      )}

      <ul className="market-events__list" data-testid="events-list">
        {events.length === 0 && data && !loading ? (
          <li className="muted">No events from available feeds in range.</li>
        ) : null}
        {events.map((ev) => (
          <li
            key={ev.id}
            className="market-events__item"
            data-testid="event-row"
            data-content-kind={ev.content_kind}
            data-feed-status={ev.feed_status}
            data-presented-as-current={
              ev.presented_as_current === true || ev.is_current === true
                ? 'true'
                : 'false'
            }
          >
            <div className="market-events__item-head">
              <strong>{ev.title}</strong>
              <span className="chip">{ev.status}</span>
              <span className="chip muted">{ev.content_kind_label || ev.content_kind}</span>
              {ev.changed ? <span className="chip is-down">changed</span> : null}
              {ev.feed_status === 'stale' ||
              ev.presented_as_current === false ||
              ev.is_current === false ? (
                <span className="chip is-down" data-testid="event-not-current">
                  STALE — not current
                </span>
              ) : null}
            </div>
            <div className="market-events__meta muted">
              <span>
                {ev.event_time_local} ({ev.timezone})
              </span>
              <span>UTC {ev.event_time_utc}</span>
              <span>
                source: {ev.source?.label || ev.source?.id}
                {ev.source?.last_updated
                  ? ` · updated ${ev.source.last_updated}`
                  : ''}
              </span>
            </div>
            {ev.outcome && (ev.outcome.value != null || ev.outcome.summary) ? (
              <p className="market-events__outcome" data-testid="event-outcome">
                Reported outcome: {ev.outcome.summary || String(ev.outcome.value)}
              </p>
            ) : null}
            {ev.model_commentary ? (
              <p className="banner warn" data-testid="event-model-commentary">
                Model commentary (not a fact): {ev.model_commentary}
              </p>
            ) : (
              <p className="muted market-events__no-model">
                No model-generated commentary.
              </p>
            )}
            {ev.previous ? (
              <p className="muted">
                Prior: {ev.previous.title} @ {ev.previous.event_time_utc}
              </p>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
