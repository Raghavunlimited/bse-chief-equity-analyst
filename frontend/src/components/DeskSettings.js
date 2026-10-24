import React, { useEffect, useState } from 'react';

const KEY = 'swing_desk_llm_key';
const PROVIDER = 'swing_desk_llm_provider';

export default function DeskSettings({ open, onClose }) {
  const [key, setKey] = useState('');
  const [provider, setProvider] = useState('openai');
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!open) return;
    try {
      setKey(localStorage.getItem(KEY) || '');
      setProvider(localStorage.getItem(PROVIDER) || 'openai');
    } catch {
      /* ignore */
    }
    setSaved(false);
  }, [open]);

  if (!open) return null;

  const save = () => {
    try {
      if (key.trim()) localStorage.setItem(KEY, key.trim());
      else localStorage.removeItem(KEY);
      localStorage.setItem(PROVIDER, provider);
      setSaved(true);
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="settings-backdrop" role="dialog" aria-modal="true">
      <div className="settings-panel">
        <header className="settings-panel__head">
          <h3>Desk settings</h3>
          <button type="button" className="btn ghost" onClick={onClose}>
            Close
          </button>
        </header>
        <p className="section-sub">
          Optional BYO LLM key for <em>Analyze with LLM</em> on consultant calls. Stored
          only in this browser; sent to our API solely when you click Analyze (then
          forwarded to the provider — never logged).
        </p>
        <label className="capital-desk__field">
          <span>Provider</span>
          <select value={provider} onChange={(e) => setProvider(e.target.value)}>
            <option value="openai">OpenAI</option>
            <option value="anthropic">Anthropic</option>
          </select>
        </label>
        <label className="capital-desk__field">
          <span>API key</span>
          <input
            type="password"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder="sk-… or anthropic key"
            autoComplete="off"
          />
        </label>
        <div className="settings-panel__actions">
          <button type="button" className="btn primary" onClick={save}>
            Save locally
          </button>
          {saved && <span className="ok-text">Saved</span>}
        </div>
      </div>
    </div>
  );
}
