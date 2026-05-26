import { Link, Outlet, useNavigate } from "react-router-dom";
import { logout } from "../api/auth";
import { setAuthed } from "../routes/ProtectedRoute";

export function AppShell() {
  const navigate = useNavigate();

  const signOut = async () => {
    await logout();
    setAuthed(false);
    navigate("/login");
  };

  return (
    <div className="app-shell">
      <header className="app-header">
        <Link to="/projects" className="app-brand">
          Pandora
        </Link>
        <button
          type="button"
          className="btn btn-ghost btn-auto"
          onClick={() => void signOut()}
        >
          Sign out
        </button>
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
