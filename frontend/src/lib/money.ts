/** Currency value from the diagnosis API: an ISO 4217 code, or "unset" when the plant has no tariff. */
export const CURRENCY_UNSET = "unset";

export function formatMoney(amount: number, currency: string | null | undefined): string {
  if (!currency || currency.toLowerCase() === CURRENCY_UNSET) return "Not estimated";
  try {
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: currency.toUpperCase(),
      maximumFractionDigits: 0,
    }).format(amount);
  } catch {
    // Unknown currency code: show the code rather than guessing a symbol.
    return `${currency.toUpperCase()} ${Math.round(amount).toLocaleString("en-IN")}`;
  }
}
