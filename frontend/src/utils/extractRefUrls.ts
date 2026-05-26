/** Strip common trailing characters that stick to pasted URLs. */
function trimTrailingJunk(url: string): string {
  return url.replace(/[),.;:!?]+$/g, "");
}

export interface ExtractRefUrlsResult {
  nextText: string;
  added: string[];
  /** URLs found in text but not attached because the limit was reached. */
  rejected: string[];
}

/**
 * Pull http(s) URLs out of free text into a reference list (max total with `existing`).
 * Removes extracted spans from text. URLs already in `existing` are removed from text only.
 * URLs beyond `maxTotal` are listed in `rejected` and stripped from text.
 */
export function extractRefUrlsFromText(
  text: string,
  existing: readonly string[],
  maxTotal: number,
): ExtractRefUrlsResult {
  const re = /https?:\/\/[^\s<>'"]+/gi;
  const seen = new Set(existing.map((u) => u.toLowerCase()));
  const added: string[] = [];
  const rejected: string[] = [];
  const toRemove: { from: number; to: number }[] = [];

  for (const m of text.matchAll(re)) {
    const raw = m[0];
    const idx = m.index ?? 0;
    const url = trimTrailingJunk(raw);
    const key = url.toLowerCase();

    if (seen.has(key)) {
      toRemove.push({ from: idx, to: idx + raw.length });
      continue;
    }

    if (existing.length + added.length >= maxTotal) {
      rejected.push(url);
      toRemove.push({ from: idx, to: idx + raw.length });
      continue;
    }

    seen.add(key);
    added.push(url);
    toRemove.push({ from: idx, to: idx + raw.length });
  }

  let next = text;
  for (const { from, to } of toRemove.sort((a, b) => b.from - a.from)) {
    next = next.slice(0, from) + next.slice(to);
  }
  next = next
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .replace(/^\s*\n+/, "");
  return { nextText: next.trimEnd(), added, rejected };
}
