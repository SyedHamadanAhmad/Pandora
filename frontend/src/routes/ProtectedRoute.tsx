import { Navigate, Outlet } from "react-router-dom";

const AUTH_KEY = "pandora_authed";

export function setAuthed(value: boolean) {
  if (value) {
    sessionStorage.setItem(AUTH_KEY, "1");
  } else {
    sessionStorage.removeItem(AUTH_KEY);
  }
}

export function isAuthed(): boolean {
  return sessionStorage.getItem(AUTH_KEY) === "1";
}

export function ProtectedRoute() {
  if (!isAuthed()) {
    return <Navigate to="/login" replace />;
  }
  return <Outlet />;
}
