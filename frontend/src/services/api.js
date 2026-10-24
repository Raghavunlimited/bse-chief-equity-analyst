import axios from 'axios';

const SESSION_KEY = 'swing_desk_session';

export function getSessionToken() {
  try {
    return localStorage.getItem(SESSION_KEY) || '';
  } catch {
    return '';
  }
}

export function setSessionToken(token) {
  try {
    if (token) localStorage.setItem(SESSION_KEY, token);
    else localStorage.removeItem(SESSION_KEY);
  } catch {
    /* ignore */
  }
}

export function clearSession() {
  setSessionToken('');
}

const api = axios.create({
  baseURL: '',
  timeout: 90000,
});

api.interceptors.request.use((config) => {
  const token = getSessionToken();
  if (token) {
    config.headers = config.headers || {};
    config.headers['X-Session-Token'] = token;
    // Session auth uses Bearer; do not overwrite with LLM keys
    if (!config.headers.Authorization) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

/** Prefer consultant desk; fall back to legacy tape on 404/network miss. */
async function consultantOrFallback(consultantPath, fallbackFn) {
  try {
    const res = await api.get(consultantPath);
    return { ...res, data: { ...res.data, _source: 'consultant' } };
  } catch (e) {
    const status = e.response?.status;
    if (status && status !== 404 && status < 500) throw e;
    const res = await fallbackFn();
    return { ...res, data: { ...res.data, _source: 'legacy' } };
  }
}

export const deskAPI = {
  health: () => api.get('/api/health'),
  authStatus: () => api.get('/api/auth/status'),
  login: (body) => api.post('/api/auth/login', body),
  register: (body) => api.post('/api/auth/register', body),
  logout: () => api.post('/api/auth/logout'),
  me: () => api.get('/api/auth/me'),

  platformDisclosure: () => api.get('/api/platform/disclosure'),
  platformSignals: ({ category, history = false, limit = 100, symbol } = {}) =>
    api.get('/api/platform/signals', {
      params: { category, history, limit, symbol },
    }),
  platformDemoSignals: () => api.get('/api/platform/demo/signals'),
  platformInstruments: (category) =>
    api.get('/api/platform/instruments', { params: { category } }),
  marketQuote: (symbol, category = 'swing') =>
    api.get(`/api/platform/market/${symbol}/quote`, { params: { category } }),
  methodology: () => api.get('/api/methodology'),

  llmVaultStatus: () => api.get('/api/me/llm'),
  llmVaultPut: (body) => api.put('/api/me/llm', body),
  llmVaultDelete: () => api.delete('/api/me/llm'),

  adminInstruments: (category) =>
    api.get('/api/admin/instruments', { params: { category } }),
  adminUpsertInstrument: (body) => api.post('/api/admin/instruments', body),
  adminPublishSignal: (body) => api.post('/api/admin/signals', body),
  adminReviseSignal: (id, body) => api.post(`/api/admin/signals/${id}/revise`, body),
  adminAudit: (limit = 100) => api.get('/api/admin/audit', { params: { limit } }),

  getStats: () => api.get('/api/stats'),
  ingestLatest: (force = false) =>
    api.post(`/api/ingest/latest?force=${force ? 'true' : 'false'}`),
  getIngestProgress: () => api.get('/api/ingest/progress'),
  ingestStatus: () => api.get('/api/ingest/status'),
  kotakStatus: () => api.get('/api/feeds/kotak'),
  testKotak: () => api.post('/api/feeds/kotak/test'),
  getWeeklyPicks: ({
    asOf,
    capital,
    risk_pct,
    max_positions,
    reserved_cash_pct,
    entry_style,
    target_gain_pct,
  } = {}) =>
    api.get('/api/weekly-picks', {
      params: {
        ...(asOf ? { as_of: asOf } : {}),
        ...(capital != null ? { capital } : {}),
        ...(risk_pct != null ? { risk_pct } : {}),
        ...(max_positions != null ? { max_positions } : {}),
        ...(reserved_cash_pct != null ? { reserved_cash_pct } : {}),
        ...(entry_style ? { entry_style } : {}),
        ...(target_gain_pct != null ? { target_gain_pct } : {}),
      },
    }),
  getMarketRegime: () => api.get('/api/market-regime'),
  runBacktest: (body = {}) => api.post('/api/backtest', body),
  getStock: (symbol) => api.get(`/api/stock/${symbol}`),
  getChart: (symbol, days = 90) =>
    api.get(`/api/chart/${symbol}`, { params: { days } }),
  getFundamentals: (symbol, refresh = false) =>
    api.get(`/api/stock/${symbol}/fundamentals`, { params: { refresh } }),
  searchStocks: (q) => api.get('/api/stocks/search', { params: { q } }),
  listStocks: ({ q = '', page = 1, page_size = 72, in_db_only = false } = {}) =>
    api.get('/api/stocks', {
      params: { q, page, page_size, in_db_only },
    }),
  getJournal: (week) =>
    api.get('/api/journal', { params: week ? { week } : {} }),
  saveJournal: (entry) => api.post('/api/journal', entry),
  getIntradaySignals: (limit = 20) =>
    api.get('/api/intraday/signals', { params: { limit } }),
  getMcxSignals: () => api.get('/api/mcx/signals'),

  getConsultantSwing: () => api.get('/api/consultant/swing'),
  getConsultantIntraday: (limit = 20) =>
    api.get('/api/consultant/intraday', { params: { limit } }),
  getConsultantMcx: () => api.get('/api/consultant/mcx'),

  getIntradayDesk: (limit = 20) =>
    consultantOrFallback(`/api/consultant/intraday?limit=${limit}`, () =>
      deskAPI.getIntradaySignals(limit),
    ),
  getMcxDesk: () =>
    consultantOrFallback('/api/consultant/mcx', () => deskAPI.getMcxSignals()),
  getSwingConsultant: async () => {
    try {
      const res = await api.get('/api/consultant/swing');
      return { ...res, data: { ...res.data, _source: 'consultant' } };
    } catch (e) {
      if (e.response?.status === 404) return { data: null };
      throw e;
    }
  },

  /**
   * LLM analysis — prefers server vault (use_stored_key).
   * Optional ephemeral apiKey in body only (never as Authorization — session uses that).
   */
  analyzeSignal: ({ provider, model, signal, context, apiKey, useStoredKey = true }) =>
    api.post(
      '/api/analyze',
      {
        provider,
        ...(model ? { model } : {}),
        signal,
        ...(context ? { context } : {}),
        ...(apiKey ? { api_key: apiKey } : {}),
        use_stored_key: useStoredKey,
      },
      { timeout: 120000 },
    ),
};

export default deskAPI;
