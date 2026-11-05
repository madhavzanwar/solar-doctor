/** SolarDoctor wordmark (DESIGN.md §9): "Doctor" is sun on dark surfaces, field on paper. */
export function Logo({ onDark = false }: { onDark?: boolean }) {
  return (
    <>
      Solar
      <strong
        style={{
          fontWeight: "inherit",
          color: onDark ? "var(--sun-ink-on-dark, #e0a24a)" : "var(--field)",
        }}
      >
        Doctor
      </strong>
    </>
  );
}
