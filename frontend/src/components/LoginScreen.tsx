import { useState } from "react";
import type { FormEvent } from "react";
import { api, errorMessage } from "../api";
import { Icon } from "../icons";
import { Logo } from "./Logo";

export function LoginScreen({ onSuccess }: { onSuccess: () => void }) {
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!token.trim() || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.login(token.trim());
      onSuccess();
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login">
      <form className="login-card" onSubmit={submit}>
        <Logo />
        <div className="login-copy">
          <h1>Welcome back</h1>
          <p>Enter the access token configured on this server.</p>
        </div>
        <label className="field">
          <span>Access token</span>
          <input
            type="password"
            value={token}
            onChange={(event) => setToken(event.target.value)}
            autoFocus
            autoComplete="current-password"
            placeholder="CRATE_TOKEN"
          />
        </label>
        {error && (
          <p className="form-error" role="alert">
            <Icon name="close" size={14} />
            {error}
          </p>
        )}
        <button type="submit" className="btn btn-primary btn-block" disabled={!token.trim() || busy}>
          {busy ? "Signing in…" : "Unlock library"}
        </button>
        <p className="login-hint">
          The token is the value of <code>CRATE_TOKEN</code> on the machine running crate.
        </p>
      </form>
    </div>
  );
}
