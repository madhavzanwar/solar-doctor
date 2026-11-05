/** Provenance badge (DESIGN.md §10): shown whenever the data source is mock or simulated. */
export function isSimulatedSource(source: string | null | undefined): boolean {
  const s = source?.trim().toLowerCase();
  return s === "mock" || s === "simulated";
}

export function SourceBadge({ source }: { source: string | null | undefined }) {
  if (!isSimulatedSource(source)) return null;
  const label = source!.trim().toLowerCase() === "mock" ? "MOCK" : "SIMULATED";
  return (
    <span
      className="dash-badge dash-badge-muted"
      title="This data is not from a live plant"
      data-testid="source-badge"
    >
      {label}
    </span>
  );
}
