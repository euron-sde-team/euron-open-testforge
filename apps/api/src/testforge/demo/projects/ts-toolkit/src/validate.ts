const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * Whether a string looks like an email address.
 * @example
 * isEmail("ada@example.com") // => true
 * isEmail("not an email") // => false
 */
export function isEmail(value: string): boolean {
  return EMAIL.test(value);
}

/**
 * Keep a number inside [min, max].
 * @example
 * clamp(15, 0, 10) // => 10
 * clamp(-2, 0, 10) // => 0
 */
export function clamp(value: number, min: number, max: number): number {
  if (min > max) {
    throw new RangeError("min must not be greater than max");
  }
  return Math.min(Math.max(value, min), max);
}
