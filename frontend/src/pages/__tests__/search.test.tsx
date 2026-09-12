/** Search pages preserve authorization evidence, bounded pagination and query privacy. */
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import SearchPage from "@/pages/search";
import { json, renderApp, type RenderAppOptions } from "@/test-support/render";
import { aSearchResult, searchResponse, searchStatus } from "@/test-support/search";

function results(options: RenderAppOptions = {}) {
  return renderApp(<SearchPage />, {
    at: "/search?q=bracket",
    ...options,
    routes: {
      "GET /api/v1/search/status": json(searchStatus()),
      "GET /api/v1/search?": json(searchResponse({ items: [aSearchResult()], outcome: "results" })),
      ...options.routes,
    },
  });
}
afterEach(() => vi.unstubAllGlobals());
describe("Search results", () => {
  it("uses the Model query endpoint without sending a name or image", async () => {
    const app = results({
      at: "/search?model=17",
      routes: {
        "GET /api/v1/models/17/similar-text?": (_url, init) => {
          expect(init?.cache).toBe("no-store");
          return json(searchResponse({ items: [aSearchResult()] }));
        },
      },
    });
    expect(await screen.findByRole("link", { name: "Desk bracket" })).toBeVisible();
    expect(screen.getByText("Find related Models", { selector: "p" })).toBeVisible();
    expect(app.requestsWithMethod("POST")).toHaveLength(0);
    expect(app.requests().some((request) => request.url.includes("/search?q="))).toBe(false);
  });
  it("clears an image query without retaining its data", async () => {
    const user = userEvent.setup();
    const preview = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:private-query");
    const revoke = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    const image = new File(["image bytes"], "private-location.png", { type: "image/png" });
    const app = results({
      at: "/search?image=1",
      routes: {
        "GET /api/v1/search/status": json(
          searchStatus({ enabled: true, semantic_ready: true, legs: ["lexical", "thumbnail"] }),
        ),
        "POST /api/v1/search/image?": (_url, init) => {
          expect(init?.body).toBe(image);
          expect(init?.cache).toBe("no-store");
          return json(
            searchResponse({
              items: [
                aSearchResult({
                  evidence: [{ leg: "thumbnail", field: "visual", text: "", ranges: [] }],
                }),
              ],
            }),
          );
        },
      },
    });
    const input = await screen.findByLabelText("Choose image", { selector: "input" });
    await waitFor(() => expect(input).toBeEnabled());
    await user.upload(input, image);
    expect(await screen.findByRole("link", { name: "Desk bracket" })).toBeVisible();
    expect(screen.getByText("Appearance match")).toBeVisible();
    expect(screen.getByRole("img", { name: "Image used for this search" })).toHaveAttribute(
      "src",
      "blob:private-query",
    );
    expect(app.requests().some((request) => request.url.includes("private-location"))).toBe(false);
    expect(preview).toHaveBeenCalledWith(image);
    await user.click(screen.getByRole("button", { name: "Clear image" }));
    expect(screen.queryByRole("link", { name: "Desk bracket" })).toBeNull();
    expect(screen.queryByRole("img")).toBeNull();
    expect(revoke).toHaveBeenCalledWith("blob:private-query");
  });
  it("requires a ready visual index before accepting images", async () => {
    const app = results({ at: "/search?image=1" });
    expect(await screen.findByText(/Visual search needs a ready visual index/)).toBeVisible();
    expect(screen.getByLabelText("Choose image", { selector: "input" })).toBeDisabled();
    expect(app.requestsWithMethod("POST")).toHaveLength(0);
  });
  it("rejects oversized image selection before sending it", async () => {
    const user = userEvent.setup();
    const app = results({
      at: "/search?image=1",
      routes: { "GET /api/v1/search/status": json(searchStatus({ legs: ["thumbnail"] })) },
    });
    const input = await screen.findByLabelText("Choose image", { selector: "input" });
    await waitFor(() => expect(input).toBeEnabled());
    await user.upload(
      input,
      new File([new Uint8Array(8 * 1024 * 1024 + 1)], "large.png", { type: "image/png" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("no larger than 8 MB");
    expect(app.requestsWithMethod("POST")).toHaveLength(0);
  });
  it("shows a shared excerpt once with both match reasons", async () => {
    const lexical = {
      leg: "lexical",
      field: "description",
      text: "Two bolts secure the bracket.",
      ranges: [],
    };
    results({
      routes: {
        "GET /api/v1/search?": json(
          searchResponse({
            items: [aSearchResult({ evidence: [lexical, { ...lexical, leg: "semantic_text" }] })],
          }),
        ),
      },
    });
    expect(await screen.findByText("Two bolts secure the bracket.")).toBeVisible();
    expect(screen.getAllByText("Two bolts secure the bracket.")).toHaveLength(1);
    expect(screen.getByText("Keyword match")).toBeVisible();
    expect(screen.getByText("Related description")).toBeVisible();
  });
  it("restarts at the first page after a generation expires the cursor", async () => {
    const user = userEvent.setup();
    const app = results({
      routes: {
        "GET /api/v1/search?": (url) =>
          url.includes("cursor=")
            ? json({ detail: "search_cursor_expired" }, 409)
            : json(searchResponse({ items: [aSearchResult()], next_cursor: "old-generation" })),
      },
    });
    await user.click(await screen.findByRole("button", { name: "Load more results" }));
    const restart = await screen.findByRole("button", { name: "Restart search" });
    app.route({
      "GET /api/v1/search?": json(
        searchResponse({ items: [aSearchResult({ name: "Current bracket" })] }),
      ),
    });
    await user.click(restart);
    expect(await screen.findByRole("link", { name: "Current bracket" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Desk bracket" })).toBeNull();
    expect(app.requests().filter((request) => request.url.includes("cursor=")).length).toBe(1);
  });
  it("renders authorized evidence for every Subject type", async () => {
    const items = [
      aSearchResult(),
      aSearchResult({
        subject_type: "collection",
        subject_id: 3,
        name: "Tools",
        href: "/?c=Tools",
      }),
      aSearchResult({
        subject_type: "multipart_model",
        subject_id: 4,
        name: "Robot",
        href: "/multipart-models/4",
      }),
      aSearchResult({
        subject_type: "document",
        subject_id: 5,
        name: "Guide",
        href: "/documents/5",
        evidence: [
          {
            leg: "semantic_text",
            field: "text",
            text: "😀 <script>bracket</script>",
            ranges: [[10, 17]],
          },
        ],
      }),
    ];
    results({ routes: { "GET /api/v1/search?": json(searchResponse({ items })) } });
    expect(await screen.findByRole("link", { name: "Desk bracket" })).toHaveAttribute(
      "href",
      "/models/12",
    );
    expect(screen.getByRole("link", { name: "Tools" })).toHaveAttribute("href", "/?c=Tools");
    expect(screen.getByRole("link", { name: "Robot" })).toHaveAttribute(
      "href",
      "/multipart-models/4",
    );
    expect(screen.getByRole("link", { name: "Guide" })).toHaveAttribute("href", "/documents/5");
    expect(screen.getByText("Related description")).toBeVisible();
    expect(document.querySelector("script")).toBeNull();
    expect([...document.querySelectorAll("mark")].map((node) => node.textContent)).toContain(
      "bracket",
    );
  });
  it("runs hybrid retrieval only for a submitted route", async () => {
    const app = results();
    await screen.findByRole("link", { name: "Desk bracket" });
    expect(app.requests().find((request) => request.url.includes("q=bracket"))?.url).toContain(
      "mode=hybrid",
    );
  });
  it("renders degraded search without losing available results", async () => {
    results({
      routes: {
        "GET /api/v1/search?": json(
          searchResponse({ items: [aSearchResult()], degraded: ["search_semantic_unavailable"] }),
        ),
      },
    });
    expect(await screen.findByText(/Some search capabilities are unavailable/)).toBeVisible();
    expect(screen.getByRole("link", { name: "Desk bracket" })).toBeVisible();
  });
  it("renders no strong matches honestly", async () => {
    results({
      routes: { "GET /api/v1/search?": json(searchResponse({ outcome: "no_strong_matches" })) },
    });
    expect(await screen.findByText("No strong matches")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Load more results" })).toBeNull();
  });
  it("loads the next opaque cursor without repeating the first page", async () => {
    const user = userEvent.setup();
    const app = results({
      routes: {
        "GET /api/v1/search?": (url) =>
          json(
            searchResponse(
              url.includes("cursor=next-page")
                ? {
                    items: [
                      aSearchResult({ subject_id: 14, name: "Second bracket", href: "/models/14" }),
                    ],
                  }
                : { items: [aSearchResult()], next_cursor: "next-page" },
            ),
          ),
      },
    });
    await user.click(await screen.findByRole("button", { name: "Load more results" }));
    expect(await screen.findByRole("link", { name: "Second bracket" })).toBeVisible();
    expect(screen.getAllByRole("link", { name: "Desk bracket" })).toHaveLength(1);
    expect(app.requests().some((request) => request.url.includes("cursor=next-page"))).toBe(true);
  });
  it("applies Subject filters through the canonical URL", async () => {
    const user = userEvent.setup();
    const app = results();
    await user.click(screen.getByRole("button", { name: "Document" }));
    await waitFor(() =>
      expect(app.requests().some((request) => request.url.includes("types%5B%5D=document"))).toBe(
        true,
      ),
    );
  });
  it("offers recovery after a failed search", async () => {
    const user = userEvent.setup();
    const app = results({ routes: { "GET /api/v1/search?": json({}, 503) } });
    const retry = await screen.findByRole("button", { name: "Retry" });
    app.route({ "GET /api/v1/search?": json(searchResponse({ items: [aSearchResult()] })) });
    await user.click(retry);
    expect(await screen.findByRole("link", { name: "Desk bracket" })).toBeVisible();
  });
});
