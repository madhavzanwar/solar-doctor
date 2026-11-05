import { describe, expect, it } from "vitest";
import { PASSWORD_MAX, PASSWORD_MIN, validatePassword } from "@/lib/password";

describe("validatePassword", () => {
  it("matches the backend contract of 10 to 256 characters", () => {
    expect(PASSWORD_MIN).toBe(10);
    expect(PASSWORD_MAX).toBe(256);
    expect(validatePassword("123456789")).toMatch(/at least 10/);
    expect(validatePassword("1234567890")).toBeNull();
    expect(validatePassword("x".repeat(256))).toBeNull();
    expect(validatePassword("x".repeat(257))).toMatch(/at most 256/);
  });
});
