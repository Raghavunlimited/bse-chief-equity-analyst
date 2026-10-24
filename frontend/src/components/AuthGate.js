import React, { useEffect, useState } from 'react';
import { deskAPI, clearSession, getSessionToken, setSessionToken } from '../services/api';

export default function AuthGate({ children, onUser }) {
  const [status, setStatus] = useState(null);
  const [user, setUser] = useState(null);
  const [email, setEmail] = useState('customer@swingdesk.local');
  const [password, setPassword] = useState('Customer1!');
  const [mode, setMode] = useState('login');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await deskAPI.authStatus();
        if (cancelled) return;
        setStatus(data);
        if (!data.auth_enabled) {
          setUser({ email: 'dev@local', role: 'admin', display_name: 'Local Dev' });
          onUser?.({ email: 'dev@local', role: 'admin' });
          return;
        }
        if (data.user && getSessionToken()) {
          setUser(data.user);
          onUser?.(data.user);
        } else if (getSessionToken()) {
          try {
            const me = await deskAPI.me();
            setUser(me.data);
            onUser?.(me.data);
          } catch {
            clearSession();
          }
        }
      } catch (e) {
        if (!cancelled) setError('Cannot reach API for auth status');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [onUser]);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const fn = mode === 'register' ? deskAPI.register : deskAPI.login;
      const { data } = await fn({ email, password });
      setSessionToken(data.token);
      setUser(data.user);
      onUser?.(data.user);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Auth failed');
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    try {
      await deskAPI.logout();
    } catch {
      /* ignore */
    }
    clearSession();
    setUser(null);
    onUser?.(null);
  }

  if (status && status.auth_enabled && !user) {
    return (
      <div className="auth-gate">
        <div className="auth-card">
          <p className="auth-brand">Swing Desk</p>
          <h1>{mode === 'login' ? 'Sign in' : 'Create account'}</h1>
          <p className="auth-blurb">
            Research analysis and signals — not investment advice. Demo accounts ship with the seed.
          </p>
          <div className="auth-demo-hint" role="note">
            Demo: customer@swingdesk.local / Customer1! · admin@swingdesk.local / AdminDemo1!
          </div>
          <form onSubmit={submit}>
            <label>
              Email
              <input
                type="email"
                value={email}
                onChange={(ev) => setEmail(ev.target.value)}
                autoComplete="username"
                required
              />
            </label>
            <label>
              Password
              <input
                type="password"
                value={password}
                onChange={(ev) => setPassword(ev.target.value)}
                autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                required
                minLength={8}
              />
            </label>
            {error ? <p className="auth-error">{String(error)}</p> : null}
            <button type="submit" disabled={busy}>
              {busy ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Register'}
            </button>
          </form>
          <button
            type="button"
            className="auth-switch"
            onClick={() => setMode(mode === 'login' ? 'register' : 'login')}
          >
            {mode === 'login' ? 'Need an account? Register' : 'Have an account? Sign in'}
          </button>
        </div>
      </div>
    );
  }

  if (!status && !user) {
    return (
      <div className="auth-gate">
        <p className="auth-loading">Checking session…</p>
      </div>
    );
  }

  return (
    <>
      {user ? (
        <div className="auth-bar" role="banner">
          <span>
            {user.display_name || user.email}
            {user.role === 'admin' ? ' · Admin' : ''}
          </span>
          {status?.auth_enabled ? (
            <button type="button" className="auth-logout" onClick={logout}>
              Sign out
            </button>
          ) : (
            <span className="auth-dev">AUTH off (local)</span>
          )}
        </div>
      ) : null}
      {children}
    </>
  );
}
