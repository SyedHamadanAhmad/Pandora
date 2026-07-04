import { useEffect, useState } from "react";
import { Navigate, Outlet } from "react-router-dom";
import { getMe } from "../api/auth";

export function ProtectedRoute() {
  const [status, setStatus] = useState<"loading" | "ok" | "guest">("loading");

  useEffect(() => {
    let cancelled = false;
    void getMe()
      .then(() => {
        if (!cancelled) setStatus("ok");
      })
      .catch(() => {
        if (!cancelled) setStatus("guest");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (status === "loading") {
    return null;
  }
  if (status === "guest") {
    return <Navigate to="/login" replace />;
  }
  return <Outlet />;
}
