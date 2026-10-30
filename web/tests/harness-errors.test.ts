import { it, expect, vi } from "vitest";
vi.mock("../src/server/security", () => ({
  ApiError: class extends Error {
    constructor(
      public status: number,
      message: string,
    ) {
      super(message);
    }
  },
}));
import { harness } from "../src/server/harness";
it("only exposes predefined safe domain errors, never arbitrary Harness response bodies", async () => {
  process.env.HARNESS_SERVICE_TOKEN = "test-service-token";
  const mock = vi.spyOn(globalThis, "fetch");
  try {
    mock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          error: {
            code: "context_data_missing",
            message: "private-provider-response",
          },
        }),
        { status: 409 },
      ),
    );
    await expect(harness("/test")).rejects.toMatchObject({
      status: 409,
      message: "context.data/manifest.json does not exist; prepare data first",
    });
    mock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          error: { code: "provider_error", message: "private-api-key" },
        }),
        { status: 400 },
      ),
    );
    await expect(harness("/test")).rejects.toMatchObject({
      status: 400,
      message: "Harness operation failed (400)",
    });
  } finally {
    mock.mockRestore();
  }
});
