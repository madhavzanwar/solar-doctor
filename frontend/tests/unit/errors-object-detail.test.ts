import { describe, expect, it } from "vitest";
import { ApiError, errorFromResponse, isTrackerUnsupported, messageFromBody } from "@/lib/api/errors";

describe("object-style detail (baseline_unsupported_for_trackers)", () => {
  const body = {
    detail: { status: "baseline_unsupported_for_trackers", message: "Fixed-tilt baseline invalid for trackers." },
  };
  it("reads detail.message instead of the HTTP status text", () => {
    expect(messageFromBody(body, "Unprocessable Entity")).toBe("Fixed-tilt baseline invalid for trackers.");
  });
  it("exposes detail.status as ApiError.code and isTrackerUnsupported", async () => {
    const res = new Response(JSON.stringify(body), { status: 422, statusText: "Unprocessable Entity" });
    const err = await errorFromResponse(res);
    expect(err.status).toBe(422);
    expect(err.message).toBe("Fixed-tilt baseline invalid for trackers.");
    expect(err.code).toBe("baseline_unsupported_for_trackers");
    expect(isTrackerUnsupported(err)).toBe(true);
    expect(isTrackerUnsupported(new ApiError(422, "x", { detail: "string" }))).toBe(false);
    expect(isTrackerUnsupported(new Error("x"))).toBe(false);
  });
  it("falls back when an object detail has no message", () => {
    expect(messageFromBody({ detail: { status: "x" } }, "fb")).toBe("fb");
  });
  it("still reads string, array and top-level message bodies", () => {
    expect(messageFromBody({ detail: "plain" }, "fb")).toBe("plain");
    expect(messageFromBody({ message: "top" }, "fb")).toBe("top");
  });
});
