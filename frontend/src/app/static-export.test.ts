import config from "../../next.config";
import { describe, expect, it } from "vitest";

describe("static export configuration", () => {
  it("does not require a request-time Next.js server", () => {
    expect(config.output).toBe("export");
    expect(config.images).toEqual({ unoptimized: true });
  });
});
