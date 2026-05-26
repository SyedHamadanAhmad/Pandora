export type ProjectStatus = "pending" | "running" | "completed" | "failed";

export interface Project {
  id: number;
  name: string;
  status: ProjectStatus;
  createdAt: string;
  updatedAt: string;
}
