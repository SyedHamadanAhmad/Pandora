import type { CreateThreadMessageOptions } from "./threadLimits";

export type { CreateThreadMessageOptions };
export { MAX_THREAD_IMAGES, MAX_THREAD_REF_URLS } from "./threadLimits";

export async function createThreadMessage(
  projectId: number,
  options: CreateThreadMessageOptions | string,
): Promise<{ messageId: number; pipelineId: number; status: string }> {
  const opts: CreateThreadMessageOptions =
    typeof options === "string" ? { content: options } : options;

  const body = new FormData();
  const content = opts.content?.trim() ?? "";
  if (content) body.append("content", content);
  const urls = opts.urls?.filter(Boolean) ?? [];
  if (urls.length > 0) body.append("urls", JSON.stringify(urls));
  for (const file of opts.images ?? []) {
    body.append("images", file);
  }

  const res = await fetch(`/api/projects/${projectId}/thread/`, {
    method: "POST",
    credentials: "include",
    body,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const json = (await res.json()) as { detail?: string };
      if (typeof json.detail === "string") detail = json.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }

  const data = await res.json();
  return {
    messageId: data.message_id ?? data.messageId,
    pipelineId: data.pipeline_id ?? data.pipelineId,
    status: data.status,
  };
}
