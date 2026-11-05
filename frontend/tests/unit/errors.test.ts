import { describe, expect, it } from "vitest";
import { ApiError, errorFromResponse, messageFromBody } from "@/lib/api/errors";
import { isSimulatedSource } from "@/components/ui/SourceBadge";

describe("messageFromBody", () => {
  it("uses a string detail", () => {
    expect(messageFromBody({ detail: "Invalid email or password" }, "x")).toBe("Invalid email or password");
  });
  it("flattens FastAPI validation errors", () => {
    const body = { detail: [{ loc: ["body", "email"], msg: "field required" }, { msg: "bad" }] };
    expect(messageFromBody(body, "x")).toBe("email: field required; bad");
  });
  it("falls back when the body is unusable", () => {
    expect(messageFromBody(null, "fallback")).toBe("fallback");
    expect(messageFromBody({ detail: 5 }, "fallback")).toBe("fallback");
  });
});

describe("errorFromResponse", () => {
  it("produces an ApiError carrying status and message", async () => {
    const res = new Response(JSON.stringify({ detail: "Not authenticated" }), { status: 401 });
    const err = await errorFromResponse(res);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(401);
    expect(err.message).toBe("Not authenticated");
  });
  it("handles non-JSON error bodies", async () => {
    const res = new Response("boom", { status: 502, statusText: "Bad Gateway" });
    const err = await errorFromResponse(res);
    expect(err.status).toBe(502);
    expect(err.message).toBe("Bad Gateway");
  });
});

describe("isSimulatedSource", () => {
  it("flags MOCK and SIMULATED in any case", () => {
    expect(isSimulatedSource("mock")).toBe(true);
    expect(isSimulatedSource("SIMULATED")).toBe(true);
  });
  it("does not flag real or missing sources", () => {
    expect(isSimulatedSource("PVDAQ")).toBe(false);
    expect(isSimulatedSource("NASA POWER")).toBe(false);
    expect(isSimulatedSource(null)).toBe(false);
    expect(isSimulatedSource(undefined)).toBe(false);
  });
});
