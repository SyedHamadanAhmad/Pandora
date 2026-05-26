import { apiFetch } from "./client";
import type {
  ComponentDetailResponse,
  StorybookOverview,
} from "./types";

export function getStorybookOverview(projectId: number) {
  return apiFetch<StorybookOverview>(`/api/projects/${projectId}/storybook`);
}

export function getComponentDetail(projectId: number, componentId: number) {
  return apiFetch<ComponentDetailResponse>(
    `/api/projects/${projectId}/components/${componentId}`,
  );
}

export function patchStorybookTokens(
  projectId: number,
  designTokens: Record<string, unknown>,
) {
  return apiFetch<{ designTokens: Record<string, unknown> }>(
    `/api/projects/${projectId}/storybook/tokens`,
    {
      method: "PATCH",
      body: JSON.stringify({ designTokens }),
    },
  );
}

export function reviseComponent(
  projectId: number,
  componentId: number,
  message: string,
) {
  return apiFetch<{ componentId: number; status: string }>(
    `/api/projects/${projectId}/components/${componentId}/revise`,
    {
      method: "POST",
      body: JSON.stringify({ message }),
    },
  );
}
