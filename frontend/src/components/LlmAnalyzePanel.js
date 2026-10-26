import React, { useEffect, useState } from 'react';
import { deskAPI } from '../services/api';
import {
  DEFAULT_MODEL_ID,
  LLM_MODELS,
  LOCAL_CUSTOM_PREFIX,
  isSafeLocalModelId,
  resolveModelSelection,
} from '../llmModels';
import { LLM_MODEL_STORAGE, LLM_PROVIDER_STORAGE } from './SettingsDrawer';

/**
 * Optional LLM research panel. Prefers server vault; optional one-shot key in body.
 * Supports provider=local (Ollama / LM Studio on loopback) without a cloud key.
 * Explain-only: never creates, upgrades, or alters a strategy signal.
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
  const [customLocalModel, setCustomLocalModel] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [useVault, setUseVault] = useState(true);
  const [vaultOk, setVaultOk] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const selected = resolveModelSelection({ modelId });
  const isLocal = selected.provider === 'local';

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

  useEffect(() => {
    if (isLocal) {
      setUseVault(false);
    }
  }, [isLocal]);

  const run = async () => {
    if (!signal || typeof signal !== 'object') {
      setError('No signal to analyze');
      return;
    }
    let resolved = resolveModelSelection({ modelId });
    if (resolved.provider === 'local' && customLocalModel.trim()) {
      if (!isSafeLocalModelId(customLocalModel.trim())) {
        setError('Local model name looks invalid');
        return;
      }
      resolved = resolveModelSelection({
        provider: 'local',
        model: customLocalModel.trim(),
      });
    }
    if (
      resolved.provider !== 'local' &&
      !useVault &&
      (!apiKey.trim() || apiKey.trim().length < 8)
    ) {
      setError('Paste an API key or enable server vault in Settings');
      return;
    }
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      try {
        localStorage.setItem(LLM_PROVIDER_STORAGE, resolved.provider);
        localStorage.setItem(
          LLM_MODEL_STORAGE,
          resolved.modelId.startsWith(LOCAL_CUSTOM_PREFIX)
            ? resolved.modelId
            : resolved.modelId,
        );
      } catch {
        /* ignore */
      }
      const { data } = await deskAPI.analyzeSignal({
        provider: resolved.provider,
        model: resolved.model,
        ...(resolved.provider === 'local'
          ? { useStoredKey: false }
          : {
              ...(useVault ? {} : { apiKey: apiKey.trim() }),
              useStoredKey: useVault,
            }),
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
            Explicit opt-in. The model may only explain this existing research card and
            must disclose missing or stale inputs. It cannot create, upgrade, or change
            BUY/SELL/HOLD. Not an order and not a return guarantee. Vault configured:{' '}
            {vaultOk ? 'yes' : 'no'}.
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
          {isLocal ? (
            <>
              <p className="muted">
                Local OpenAI-compatible server (Ollama default{' '}
                <code>http://127.0.0.1:11434/v1</code>, or LM Studio{' '}
                <code>http://127.0.0.1:1234/v1</code>). Set{' '}
                <code>LOCAL_LLM_BASE_URL</code> in <code>backend/.env</code>. No cloud
                API key required. Pull the model first (e.g.{' '}
                <code>ollama pull llama3.2</code>).
              </p>
              <label className="settings-drawer__field">
                <span>Custom local model tag (optional)</span>
                <input
                  type="text"
                  value={customLocalModel}
                  onChange={(e) => setCustomLocalModel(e.target.value)}
                  placeholder="e.g. llama3.2:latest"
                  autoComplete="off"
                  spellCheck={false}
                />
              </label>
            </>
          ) : (
            <>
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
            </>
          )}
          <button type="button" className="btn primary" onClick={run} disabled={loading}>
            {loading ? 'Explaining…' : 'Explain card (LLM — explain only)'}
          </button>
          {error ? <p className="auth-error">{error}</p> : null}
          {result ? (
            <div className="llm-panel__result">
              <p className="prov-badge prov-badge--demo">
                {result.label || 'AI-GENERATED COMMENTARY'}
                {result.analysis?.provider === 'local' || result.provider === 'local'
                  ? ' · LOCAL'
                  : ''}
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
