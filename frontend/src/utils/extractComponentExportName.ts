/**
 * Resolves the primary exported component identifier from generated TSX.
 */
export function extractComponentExportName(tsx: string, fallbackName: string): string {
  const trimmed = tsx.trim();
  const fn = trimmed.match(/export\s+function\s+([A-Za-z0-9_]+)\s*\(/);
  if (fn?.[1]) return fn[1];
  const cn = trimmed.match(/export\s+const\s+([A-Za-z0-9_]+)\s*=/);
  if (cn?.[1]) return cn[1];
  const def = trimmed.match(/export\s+default\s+function\s+([A-Za-z0-9_]+)\s*\(/);
  if (def?.[1]) return def[1];

  const safe = fallbackName.replace(/[^A-Za-z0-9_]/g, "");
  if (!safe) return "PreviewComponent";
  const pascal = safe[0]!.toUpperCase() + safe.slice(1);
  return /^[A-Za-z_]/.test(pascal) ? pascal : `C${pascal}`;
}
