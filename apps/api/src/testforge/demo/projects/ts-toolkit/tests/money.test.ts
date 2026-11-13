import { describe, expect, it } from "vitest";
import { formatPrice } from "../src/money";

describe("formatPrice", () => {
  it("formats dollars", () => {
    expect(formatPrice(1999)).toBe("$19.99");
  });
});
