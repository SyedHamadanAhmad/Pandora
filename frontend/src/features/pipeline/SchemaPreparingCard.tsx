import "./SchemaPreparingCard.css";

interface SchemaPreparingCardProps {
  skeletonCount?: number;
}

export function SchemaPreparingCard({ skeletonCount = 4 }: SchemaPreparingCardProps) {
  return (
    <article className="schema-preparing panel" aria-label="Preparing design schema">
      <header className="schema-preparing__header">
        <h2 className="schema-preparing__title">Design schema</h2>
        <p className="schema-preparing__status">Mapping components…</p>
      </header>
      <ul className="schema-preparing__skeletons" aria-hidden>
        {Array.from({ length: skeletonCount }, (_, i) => (
          <li key={i} className="schema-preparing__skeleton" />
        ))}
      </ul>
    </article>
  );
}
