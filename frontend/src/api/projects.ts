import { apiFetch } from "./client";
import type { Project } from "./types";

export async function listProjects() {
  return apiFetch<{ projects: Project[] }>("/api/projects/");
}

export async function createProject(name: string) {
  return apiFetch<Project>("/api/projects/", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}
