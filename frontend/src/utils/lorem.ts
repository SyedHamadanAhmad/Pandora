const SENTENCES = [
  "The quick brown fox jumps over the lazy dog.",
  "Design systems keep products consistent at scale.",
  "Typography sets the rhythm of every interface.",
  "Color tokens anchor brand identity across components.",
  "Spacing creates breathing room between elements.",
];

export function sampleLorem(seed?: string): string {
  const index =
    seed != null
      ? Math.abs(hashCode(seed)) % SENTENCES.length
      : Math.floor(Math.random() * SENTENCES.length);
  return SENTENCES[index]!;
}

function hashCode(value: string): number {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash << 5) - hash + value.charCodeAt(i);
    hash |= 0;
  }
  return hash;
}
