/**
 * A basket of priced items.
 * @example
 * const basket = new Basket();
 * basket.add("tea", 2, 350);
 * basket.total() // => 700
 */
export class Basket {
  private lines = new Map<string, { quantity: number; cents: number }>();

  /** Add `quantity` of an item at `cents` each. */
  add(sku: string, quantity: number, cents: number): void {
    if (quantity <= 0) {
      throw new RangeError("quantity must be positive");
    }
    const held = this.lines.get(sku)?.quantity ?? 0;
    this.lines.set(sku, { quantity: held + quantity, cents });
  }

  /**
   * How many units are in the basket.
   * @example
   * const basket = new Basket();
   * basket.add("tea", 2, 350);
   * basket.add("cup", 1, 800);
   * basket.count() // => 3
   */
  count(): number {
    let n = 0;
    for (const line of this.lines.values()) n += line.quantity;
    return n;
  }

  /** The total in cents. */
  total(): number {
    let sum = 0;
    for (const line of this.lines.values()) sum += line.quantity * line.cents;
    return sum;
  }
}
