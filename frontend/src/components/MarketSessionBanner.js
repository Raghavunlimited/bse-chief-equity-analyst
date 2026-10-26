import React, { useCallback, useEffect, useState } from 'react';
import { deskAPI } from '../services/api';

/**
 * IST session + feed hygiene banner.
 * Broker LIVE only when feed_health says LIVE/broker_live.
 * Yahoo age-fresh → FALLBACK (research), never “live broker”.
 */
export default function MarketSessionBanner({ feedHealth }) {
  const [session, setSession] = useState(null);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      const { data } = await deskAPI.getMarketSession();
      setSession(data);
      setError(null);
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Session clock unavailable');
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [load]);

  const label = session?.badge || 'SESSION UNKNOWN';
  const frozen = session?.live_ticks_frozen;
  const fh = feedHealth || {};
  const feedStatus = String(fh.market_data_state || fh.feed_status || '').toUpperCase();
  const liveAllowed = fh.live_calls_allowed;
  const brokerLive = fh.broker_live === true;

  let tone = 'post';
  let title = label;
  let detail =
    session?.note ||
    'EOD closes and LTP are separate. Swing uses EOD; Intraday/Index use LTP.';

  if (error) {
    tone = 'error';
    title = 'FEED ERROR';
    detail = String(error);
  } else if (session?.in_regular_hours) {
    if (feedStatus === 'STALE' || liveAllowed === false) {
      tone = 'stale';
      title = 'FEED STALE — CALLS HALTED · LAST OBSERVATION ONLY';
      detail =
        fh.message ||
        `Quote older than ${session?.stale_sec_threshold || 5}s. Not current live data.`;
    } else if (feedStatus === 'ERROR' || feedStatus === 'UNAVAILABLE') {
      tone = 'error';
      title = 'FEED UNAVAILABLE';
      detail = fh.message || 'Quote provider failed — refusing synthetic data.';
    } else if (feedStatus === 'LIVE' && brokerLive) {
      tone = 'live';
      title = 'BROKER LIVE · KOTAK LTP';
      detail = 'Kotak Neo WebSocket LTP within age threshold. Swing anchors remain EOD.';
    } else if (feedStatus === 'FALLBACK' || !brokerLive) {
      tone = 'fallback';
      title = 'YAHOO RESEARCH FALLBACK — NOT BROKER LIVE';
      detail =
        fh.message ||
        'Age-fresh Yahoo 5m tape for research only. Connect Kotak WS for broker LIVE.';
    } else {
      tone = 'post';
      title = 'REGULAR SESSION';
      detail =
        fh.message ||
        'Regular session — feed state neither LIVE nor FALLBACK.';
    }
  } else {
    tone = 'post';
    title = label;
    detail =
      session?.calendar_note ||
      'Live-tick triggers frozen. Desks show EOD snapshot / last residue only — not fresh LTP edge.';
  }

  return (
    <div className={`session-banner session-banner--${tone}`} role="status">
      <strong className="session-banner__title">{title}</strong>
      <span className="session-banner__detail">{detail}</span>
      {frozen ? <em className="session-banner__tag">TICKS FROZEN</em> : null}
      {feedStatus ? (
        <em className="session-banner__tag">{feedStatus}</em>
      ) : null}
      {session?.ist ? (
        <em className="session-banner__tag">{String(session.ist).slice(11, 19)} IST</em>
      ) : null}
    </div>
  );
}
