import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { login, register } from "../api/auth";
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
      navigate("/projects");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Auth failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <aside className="login-brand" aria-hidden={false}>
        <div className="login-brand__blobs" aria-hidden />
        <div className="login-brand__grid" aria-hidden />
        <div className="login-brand__inner">
          <h1 className="login-brand__title">Pandora</h1>
          <p className="login-brand__tagline">
            From idea to component library—one design pipeline.
          </p>
        </div>
      </aside>

      <section className="login-form-side">
        <div className="login-form-panel">
          <div className="login-form-intro">
            <div className="login-mark" aria-hidden>
              P
            </div>
            <p className="login-proof">Used by 200+ indie builders</p>
          </div>

          <form
            className="login-form"
            onSubmit={(e) => void submit(e, "login")}
            noValidate
          >
            <div className="field field--login">
              <label className="field-label field-label--login" htmlFor="email">
                Email
              </label>
              <input
                id="email"
                className="field-input field-input--login"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
                disabled={loading}
              />
            </div>

            <div className="field field--login field--login-last">
              <label
                className="field-label field-label--login"
                htmlFor="password"
              >
                Password
              </label>
              <input
                id="password"
                className="field-input field-input--login"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                disabled={loading}
              />
            </div>

            {error && (
              <div className="form-alert" role="alert">
                <span className="form-alert__icon" aria-hidden>
                  ⚠
                </span>
                <p className="form-alert__text">{error}</p>
              </div>
            )}

            <div className="login-form__actions">
              <button
                type="submit"
                className="btn btn-login-primary"
                disabled={loading}
              >
                {loading ? "Signing in…" : "Login"}
              </button>
              <p className="login-register-prompt">
                Don&apos;t have an account?{" "}
                <button
                  type="button"
                  className="login-register-link"
                  disabled={loading}
                  onClick={(e) => void submit(e, "register")}
                >
                  Register
                </button>
              </p>
            </div>
          </form>
        </div>
      </section>
    </div>
  );
}
