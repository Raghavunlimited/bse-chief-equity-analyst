import React, { useEffect, useState } from 'react';
import {
  DEFAULT_MODEL_ID,
  LLM_MODELS,
  findModel,
  resolveModelSelection,
} from '../llmModels';
import { deskAPI } from '../services/api';

export const LLM_PROVIDER_STORAGE = 'swing_desk_llm_provider';
export const LLM_MODEL_STORAGE = 'swing_desk_llm_model';

export function loadLlmSettings() {
  try {
    const provider = localStorage.getItem(LLM_PROVIDER_STORAGE) || 'openai';
    const modelId =
      localStorage.getItem(LLM_MODEL_STORAGE) ||
      resolveModelSelection({ provider }).modelId;
    const resolved = resolveModelSelection({ provider, modelId });
    return {
      apiKey: '', // never keep key in browser for MVP vault mode
      provider: resolved.provider,
      model: resolved.model,
      modelId: resolved.modelId,
      vaultConfigured: false,
    };
  } catch {
    const hit = findModel(DEFAULT_MODEL_ID);
    return {
      apiKey: '',
      provider: hit.provider,
      model: hit.model,
      modelId: hit.id,
      vaultConfigured: false,
    };
  }
}

export function saveLlmSettings({ provider, modelId, model }) {
  try {
    const resolved = resolveModelSelection({ provider, modelId, model });
    localStorage.setItem(LLM_PROVIDER_STORAGE, resolved.provider);
    localStorage.setItem(LLM_MODEL_STORAGE, resolved.modelId);
  } catch {
    /* ignore */
  }
}

/**
 * LLM settings — API key stored encrypted on server via /api/me/llm.
 * Key is never returned to the browser after save.
 */
export default function SettingsDrawer({ open, onClose, onSaved }) {
  const [apiKey, setApiKey] = useState('');
  const [modelId, setModelId] = useState(DEFAULT_MODEL_ID);
  const [showKey, setShowKey] = useState(false);
  const [vault, setVault] = useState({ configured: false });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    if (!open) return undefined;
    const s = loadLlmSettings();
    setApiKey('');
    setModelId(s.modelId || DEFAULT_MODEL_ID);
    setShowKey(false);
    setMsg(null);
    setErr(null);
    deskAPI
      .llmVaultStatus()
      .then((r) => setVault(r.data))
      .catch(() => setVault({ configured: false }));
    const onKey = (e) => {
      if (e.key === 'Escape') onClose?.();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  const selected = findModel(modelId);
  const provider = selected.provider;

  const save = async () => {
    setBusy(true);
    setErr(null);
    setMsg(null);
    saveLlmSettings({
      provider,
      modelId: selected.id,
      model: selected.model,
    });
    try {
      let configured = !!vault.configured;
      if (apiKey.trim()) {
        const { data } = await deskAPI.llmVaultPut({
          provider,
          api_key: apiKey.trim(),
          model: selected.model,
        });
        setVault({ configured: true, provider: data.provider, model: data.model });
        setApiKey('');
        configured = true;
        setMsg('Key saved encrypted on server. It will not be shown again.');
      } else {
        setMsg('Model preference saved. Enter a key to update the vault.');
      }
      onSaved?.({
        ...loadLlmSettings(),
        vaultConfigured: configured,
        provider,
        model: selected.model,
        modelId: selected.id,
        apiKey: '',
      });
    } catch (e) {
      setErr(e.response?.data?.detail || e.message);
    } finally {
      setBusy(false);
    }
  };

  const clear = async () => {
    setBusy(true);
    setErr(null);
    try {
      await deskAPI.llmVaultDelete();
      setVault({ configured: false });
      setApiKey('');
      setMsg('Server key deleted.');
      onSaved?.(loadLlmSettings());
    } catch (e) {
      setErr(e.response?.data?.detail || e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="modal-backdrop settings-drawer-backdrop"
      role="presentation"
      onClick={onClose}
    >
      <div
        className="modal settings-drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-drawer-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="modal__head">
          <div>
            <h2 id="settings-drawer-title">LLM settings</h2>
            <p>Optional AI commentary — key encrypted at rest on the server.</p>
          </div>
          <button type="button" className="btn ghost" onClick={onClose}>
            Close
          </button>
        </header>

        <p className="settings-drawer__note">
          Keys are <strong>never returned</strong> to the browser after save. Analysis runs
          only when you explicitly click Analyze. AI output is commentary, not an
          authoritative signal.
        </p>

        <p className="settings-drawer__vault" role="status">
          Vault:{' '}
          {vault.configured
            ? `configured (${vault.provider}${vault.model ? ` · ${vault.model}` : ''})`
            : 'not configured'}
        </p>

        <label className="settings-drawer__field">
          <span>Model</span>
          <select
            value={modelId}
            onChange={(e) => setModelId(e.target.value)}
            aria-label="LLM model"
          >
            {LLM_MODELS.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </label>

        <label className="settings-drawer__field">
          <span>{vault.configured ? 'Replace API key' : 'API key'}</span>
          <div className="settings-drawer__key-row">
            <input
              type={showKey ? 'text' : 'password'}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={
                vault.configured
                  ? '•••••••• (enter new key to replace)'
                  : provider === 'anthropic'
                    ? 'sk-ant-…'
                    : 'sk-…'
              }
              autoComplete="off"
              spellCheck={false}
              aria-label="LLM API key"
            />
            <button
              type="button"
              className="btn ghost"
              onClick={() => setShowKey((v) => !v)}
            >
              {showKey ? 'Hide' : 'Show'}
            </button>
          </div>
        </label>

        {msg ? <p className="admin-ok">{msg}</p> : null}
        {err ? <p className="auth-error">{String(err)}</p> : null}

        <div className="settings-drawer__actions">
          <button type="button" className="btn ghost" onClick={clear} disabled={busy}>
            Delete server key
          </button>
          <button type="button" className="btn primary" onClick={save} disabled={busy}>
            {busy ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
