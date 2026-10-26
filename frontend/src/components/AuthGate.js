import React, { useEffect, useState } from 'react';
import { deskAPI, clearSession, getSessionToken, setSessionToken } from '../services/api';

/**
 * Phase 1: personal desk boots straight in when AUTH_ENABLED=false.
 * Multi-user login remains available only if the API reports auth_enabled.
 */
export default function AuthGate({ children, onUser }) {
  const [status, setStatus] = useState(null);
  const [user, setUser] = useState(null);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
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
          // Local personal desk: AUTH off. Backend still authorizes admin APIs
          // via synthetic local admin — UI may show Publish notes; API stays gated
          // when AUTH_ENABLED=true.
          const op = {
            email: 'operator@local',
            role: 'operator',
            display_name: 'Personal desk',
            auth_enabled: false,
          };
          setUser(op);
          onUser?.(op);
          return;
        }
        if (data.user && getSessionToken()) {
          const u = { ...data.user, auth_enabled: true };
          setUser(u);
          onUser?.(u);
        } else if (getSessionToken()) {
          try {
            const me = await deskAPI.me();
            const u = { ...me.data, auth_enabled: true };
            setUser(u);
            onUser?.(u);
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
            Optional multi-user mode. Personal desks should run with AUTH_ENABLED=false.
          </p>
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
        <p className="auth-loading">Starting personal desk…</p>
      </div>
    );
  }

  return (
    <>
      {status?.auth_enabled && user ? (
        <div className="auth-bar" role="banner">
          <span>
            {user.display_name || user.email}
            {user.role === 'admin' ? ' · Admin' : ''}
          </span>
          <button type="button" className="auth-logout" onClick={logout}>
            Sign out
          </button>
        </div>
      ) : null}
      {children}
    </>
  );
}
