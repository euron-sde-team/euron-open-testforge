/**
 * Format an amount in cents as a price.
 * @example
 * formatPrice(1999) // => "$19.99"
 * formatPrice(5, "EUR") // => "EUR 0.05"
 */
export function formatPrice(cents: number, currency: string = "USD"): string {
  if (!Number.isInteger(cents)) {
    throw new TypeError("cents must be a whole number");
  }
  const value = (cents / 100).toFixed(2);
  return currency === "USD" ? `$${value}` : `${currency} ${value}`;
}

/**
 * Parse "12.50" or "$12.50" into cents.
 * @example
 * parseAmount("12.50") // => 1250
 * parseAmount("$3") // => 300
 */
export function parseAmount(text: string): number {
  const cleaned = text.trim().replace(/^\$/, "");
  if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) {
    throw new Error(`not an amount: ${text}`);
  }
  return Math.round(Number(cleaned) * 100);
}

/**
 * Add a percentage of tip, rounded to the cent.
 * @example
 * addTip(1000, 15) // => 1150
 */
export const addTip = (cents: number, percent: number): number => {
  if (percent < 0) throw new RangeError("percent must not be negative");
  return Math.round(cents * (1 + percent / 100));
};
