/** Roles from docs/solardoctor/API_AUTH.md, lowest to highest rank. */
const LABELS: Record<string, string> = {
  admin: "Administrator",
  operator: "Operator",
  technician: "Technician",
  viewer: "Viewer",
};

/** Label for the signed-in user's role; empty until the role is known, never a guess. */
export function roleLabel(role: string | null | undefined): string {
  if (!role) return "";
  return LABELS[role.toLowerCase()] ?? role;
}
