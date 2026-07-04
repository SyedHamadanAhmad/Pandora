import { apiFetch } from "./client";

export async function register(email: string, password: string) {
  return apiFetch<{ userId: number }>("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function login(email: string, password: string) {
  return apiFetch<{ userId: number }>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function logout() {
  return apiFetch<void>("/api/auth/logout", { method: "POST" });
}

export async function getMe() {
  return apiFetch<{ userId: number }>("/api/auth/me");
}
