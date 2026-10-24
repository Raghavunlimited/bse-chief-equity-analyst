import React, { useEffect, useState } from 'react';
import { deskAPI } from '../services/api';
import {
  DEFAULT_MODEL_ID,
  LLM_MODELS,
  resolveModelSelection,
} from '../llmModels';
import { LLM_MODEL_STORAGE, LLM_PROVIDER_STORAGE } from './SettingsDrawer';

/**
 * Optional LLM research panel. Prefers server vault; optional one-shot key in body.
 */
export default function LlmAnalyzePanel({ signal, context, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  const [modelId, setModelId] = useState(() => {
    try {
      return localStorage.getItem(LLM_MODEL_STORAGE) || DEFAULT_MODEL_ID;
    } catch {
      return DEFAULT_MODEL_ID;
    }
  });
  const [apiKey, setApiKey] = useState('');
  const [useVault, setUseVault] = useState(true);
  const [vaultOk, setVaultOk] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  useEffect(() => {
    setResult(null);
    setError(null);
  }, [signal]);

  useEffect(() => {
    if (defaultOpen) setOpen(true);
  }, [defaultOpen, signal]);

  useEffect(() => {
    if (!open) return;
    deskAPI
      .llmVaultStatus()
      .then((r) => setVaultOk(!!r.data?.configured))
      .catch(() => setVaultOk(false));
  }, [open]);

  const run = async () => {
    if (!signal || typeof signal !== 'object') {
      setError('No signal to analyze');
      return;
    }
    if (!useVault && (!apiKey.trim() || apiKey.trim().length < 8)) {
      setError('Paste an API key or enable server vault in Settings');
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const resolved = resolveModelSelection({ modelId });
      try {
        localStorage.setItem(LLM_PROVIDER_STORAGE, resolved.provider);
        localStorage.setItem(LLM_MODEL_STORAGE, resolved.modelId);
      } catch {
        /* ignore */
      }
      const { data } = await deskAPI.analyzeSignal({
        provider: resolved.provider,
        model: resolved.model,
        ...(useVault ? {} : { apiKey: apiKey.trim() }),
        useStoredKey: useVault,
        signal,
        context,
      });
      setResult(data);
      setApiKey('');
    } catch (e) {
      const detail = e.response?.data?.detail;
      setError(
        typeof detail === 'string'
          ? detail
          : Array.isArray(detail)
            ? detail.map((d) => d.msg || JSON.stringify(d)).join('; ')
            : e.message || 'Analyze failed',
      );
    } finally {
      setLoading(false);
    }
  };

  if (!signal) return null;

  return (
    <div className="llm-panel">
      <button
        type="button"
        className="btn ghost llm-panel__toggle"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? 'Hide LLM notes' : 'LLM research notes (optional)'}
      </button>

      {open && (
        <div className="llm-panel__body">
          <p className="muted">
            Explicit opt-in. Output is AI commentary citing your signal JSON — not an
            authoritative signal. Vault configured: {vaultOk ? 'yes' : 'no'}.
          </p>
          <label className="settings-drawer__field">
            <span>Model</span>
            <select value={modelId} onChange={(e) => setModelId(e.target.value)}>
              {LLM_MODELS.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>
          <label className="llm-panel__check">
            <input
              type="checkbox"
              checked={useVault}
              onChange={(e) => setUseVault(e.target.checked)}
            />
            Use encrypted server vault key
          </label>
          {!useVault && (
            <label className="settings-drawer__field">
              <span>One-shot API key (not stored)</span>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                autoComplete="off"
              />
            </label>
          )}
          <button type="button" className="btn primary" onClick={run} disabled={loading}>
            {loading ? 'Analyzing…' : 'Analyze with LLM'}
          </button>
          {error ? <p className="auth-error">{error}</p> : null}
          {result ? (
            <div className="llm-panel__result">
              <p className="prov-badge prov-badge--demo">
                {result.label || 'AI-GENERATED COMMENTARY'}
              </p>
              <p>{result.summary || result.analysis?.summary}</p>
              {result.cited_inputs ? (
                <p className="muted">
                  Cited inputs: {(result.cited_inputs.signal_keys || []).join(', ')}
                </p>
              ) : null}
              <p className="muted">{result.disclaimer}</p>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
