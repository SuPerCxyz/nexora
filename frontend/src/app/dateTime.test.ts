import { afterEach, describe, expect, it } from "vitest";

import { configureTimeZone, formatDateTime } from "./dateTime";

afterEach(() => configureTimeZone("Asia/Shanghai"));

describe("administrator time zone formatting", () => {
  it("renders UTC timestamps in Asia/Shanghai", () => {
    configureTimeZone("Asia/Shanghai");

    const formatted = formatDateTime("2026-08-01T00:00:00Z", {
      dateStyle: "short",
      timeStyle: "medium",
    });

    expect(formatted).toContain("08:00:00");
  });

  it("treats offset-free database timestamps as UTC", () => {
    configureTimeZone("Asia/Shanghai");

    const utc = formatDateTime("2026-08-01T00:00:00Z");
    const sqlite = formatDateTime("2026-08-01T00:00:00");

    expect(sqlite).toBe(utc);
  });
});
