export async function createThreadMessage(
  projectId: number,
  content: string,
): Promise<{ messageId: number; pipelineId: number; status: string }> {
  const body = new FormData();
  body.append("content", content);

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
