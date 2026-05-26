import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { login, register } from "../api/auth";
import { setAuthed } from "../routes/ProtectedRoute";
import "./LoginPage.css";

export function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async (e: FormEvent, mode: "login" | "register") => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password);
        await login(email, password);
      }
      setAuthed(true);
      navigate("/projects");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Auth failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-panel">
        <header className="login-header">
          <h1 className="login-title">Pandora</h1>
          <p className="login-tagline">
            From idea to component library—one design pipeline.
          </p>
        </header>

        <form
          className="login-form"
          onSubmit={(e) => void submit(e, "login")}
          noValidate
        >
          <div className="field">
            <label className="field-label" htmlFor="email">
              Email
            </label>
            <input
              id="email"
              className="field-input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              disabled={loading}
            />
          </div>

          <div className="field">
            <label className="field-label" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              className="field-input"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="current-password"
              disabled={loading}
            />
          </div>

          {error && (
            <p className="login-error" role="alert">
              {error}
            </p>
          )}

          <div className="login-actions">
            <button type="submit" className="btn btn-cta" disabled={loading}>
              {loading ? "…" : "Login"}
            </button>
            <button
              type="button"
              className="btn btn-dark"
              disabled={loading}
              onClick={(e) => void submit(e, "register")}
            >
              Register
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
