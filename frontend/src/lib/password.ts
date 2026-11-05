/** Backend contract (docs/solardoctor/API_AUTH.md): 10-256 characters. The server also rejects a single repeated
 * character and a password equal to the email name, and answers 400 with a readable `detail`. */
export const PASSWORD_MIN = 10;
export const PASSWORD_MAX = 256;
export const PASSWORD_HINT = `Use ${PASSWORD_MIN} to ${PASSWORD_MAX} characters.`;

export function validatePassword(password: string): string | null {
  if (password.length < PASSWORD_MIN) return `Password must be at least ${PASSWORD_MIN} characters.`;
  if (password.length > PASSWORD_MAX) return `Password must be at most ${PASSWORD_MAX} characters.`;
  return null;
}
