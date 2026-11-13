/**
 * Turn a title into a URL slug.
 * @example
 * slugify("Hello, World!") // => "hello-world"
 * slugify("  Tea & Cups  ") // => "tea-cups"
 */
export function slugify(title: string): string {
  return title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/**
 * Shorten text to at most `max` characters, ending with three dots.
 * @example
 * truncate("abcdefgh", 6) // => "abc..."
 * truncate("abc", 5) // => "abc"
 */
export function truncate(text: string, max: number): string {
  if (max < 4) {
    throw new RangeError("max must be at least 4");
  }
  return text.length <= max ? text : text.slice(0, max - 3) + "...";
}
