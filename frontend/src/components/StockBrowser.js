import React, { useCallback, useEffect, useState } from 'react';
import { deskAPI } from '../services/api';

export default function StockBrowser({ onOpen }) {
  const [q, setQ] = useState('');
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [inDbOnly, setInDbOnly] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { data: res } = await deskAPI.listStocks({
        q: q.trim(),
        page,
        page_size: 72,
        in_db_only: inDbOnly,
      });
      setData(res);
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Failed to load stocks');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [q, page, inDbOnly]);

  useEffect(() => {
    const t = setTimeout(load, q ? 220 : 0);
    return () => clearTimeout(t);
  }, [load, q]);

  useEffect(() => {
    setPage(1);
  }, [q, inDbOnly]);

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <section className="section stock-browser" id="section-stocks">
      <div className="section__head">
        <div>
          <h3>All NSE stocks</h3>
          <p className="section-sub">
            Browse listed NSE EQ cash names. Click any symbol for financials
            {data
              ? ` · ${data.total.toLocaleString('en-IN')} shown · ${data.in_database} with EOD in desk`
              : ''}
            .
          </p>
        </div>
        <label className="toggle-db">
          <input
            type="checkbox"
            checked={inDbOnly}
            onChange={(e) => setInDbOnly(e.target.checked)}
          />
          EOD in desk only
        </label>
      </div>

      <div className="stock-browser__toolbar">
        <input
          type="search"
          placeholder="Filter by symbol (e.g. RELI, TATA, BANK)…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          aria-label="Filter stocks"
        />
      </div>

      {error && <p className="error-text">{error}</p>}
      {loading && !data && <p className="muted">Loading universe…</p>}

      {data && (
        <>
          <div className="stock-grid">
            {data.results.map((row) => (
              <button
                key={row.symbol}
                type="button"
                className={`stock-chip ${row.has_eod ? 'stock-chip--eod' : ''}`}
                onClick={() => onOpen(row.symbol)}
                title={row.has_eod ? 'Has local EOD' : 'Financials only until ingested'}
              >
                <span className="stock-chip__sym">{row.symbol}</span>
                <span className="stock-chip__sec">{row.sector}</span>
              </button>
            ))}
            {data.results.length === 0 && (
              <p className="muted">No symbols match that filter.</p>
            )}
          </div>

          <div className="pager">
            <button
              type="button"
              className="btn ghost"
              disabled={page <= 1 || loading}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Previous
            </button>
            <span className="muted">
              Page {page} / {totalPages}
            </span>
            <button
              type="button"
              className="btn ghost"
              disabled={page >= totalPages || loading}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </button>
          </div>
        </>
      )}
    </section>
  );
}
