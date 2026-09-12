/** Typing uses lexical suggestions; submitting enters the explicit search flow. */
import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LibrarySearch } from "@/components/library-search";
import { usePathname, useSearchParams } from "@/lib/navigation";
import { json, renderApp, type RenderAppOptions } from "@/test-support/render";
import { aSearchResult, searchResponse, searchStatus } from "@/test-support/search";

function Location() {
  return (
    <output data-testid="location">
      {usePathname()}?{useSearchParams().toString()}
    </output>
  );
}
function searchBox(options: RenderAppOptions = {}) {
  return renderApp(
    <>
      <LibrarySearch />
      <Location />
    </>,
    {
      ...options,
      routes: {
        "GET /api/v1/search/status": json(searchStatus()),
        "GET /api/v1/search?": json(searchResponse({ items: [aSearchResult()] })),
        ...options.routes,
      },
    },
  );
}
afterEach(() => vi.unstubAllGlobals());

describe("LibrarySearch", () => {
  it("debounces lexical suggestions without inference", async () => {
    const user = userEvent.setup();
    const app = searchBox();
    await user.type(screen.getByRole("searchbox"), "bracket");
    expect(await screen.findByRole("link", { name: /Desk bracket/ })).toBeVisible();
    const requests = app.requests().filter((request) => request.url.startsWith("/api/v1/search?"));
    expect(requests).toHaveLength(1);
    expect(new URL(requests[0].url, "http://test").searchParams.get("mode")).toBe("lexical");
    expect(requests[0].url).toContain("instant=true");
  });
  it("submits the query to the results route", async () => {
    const user = userEvent.setup();
    searchBox();
    await user.type(screen.getByRole("searchbox"), "small boat{Enter}");
    expect(screen.getByTestId("location")).toHaveTextContent("/search?q=small+boat");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
  it("shows AI only when the active capability is usable", async () => {
    searchBox({
      routes: {
        "GET /api/v1/search/status": json(searchStatus({ enabled: true, semantic_ready: true })),
      },
    });
    expect(await screen.findByRole("button", { name: "Search with AI" })).toBeVisible();
  });
  it("hides AI while an index is unavailable", async () => {
    const app = searchBox({
      routes: {
        "GET /api/v1/search/status": json(searchStatus({ enabled: true, semantic_ready: false })),
      },
    });
    await waitFor(() => expect(app.requests()).toHaveLength(1));
    expect(screen.queryByRole("button", { name: "Search with AI" })).toBeNull();
  });
  it("keeps keyboard focus through suggestions", async () => {
    const user = userEvent.setup();
    searchBox();
    await user.keyboard("/");
    const input = screen.getByRole("searchbox");
    expect(input).toHaveFocus();
    await user.type(input, "bracket");
    const result = await screen.findByRole("link", { name: /Desk bracket/ });
    expect(input).toHaveFocus();
    await user.keyboard("{ArrowDown}");
    expect(result).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(input).toHaveFocus();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });
  it("ignores late suggestions for a replaced query", async () => {
    const user = userEvent.setup();
    searchBox();
    let finish: (response: Response) => void = () => {};
    const old = new Promise<Response>((resolve) => {
      finish = resolve;
    });
    const fetcher = vi.fn<typeof fetch>(async (url) =>
      String(url).includes("/status")
        ? json(searchStatus())
        : new URL(String(url), "http://localhost").searchParams.get("q") === "old"
          ? old
          : json(searchResponse({ items: [aSearchResult({ name: "Current bracket" })] })),
    );
    vi.stubGlobal("fetch", fetcher);
    const input = screen.getByRole("searchbox");
    await user.type(input, "old");
    await waitFor(() =>
      expect(fetcher.mock.calls.some(([url]) => String(url).includes("q=old"))).toBe(true),
    );
    await user.clear(input);
    await user.type(input, "new");
    expect(input).toHaveValue("new");
    expect(await screen.findByRole("link", { name: /Current bracket/ })).toBeVisible();
    await act(async () => {
      finish(json(searchResponse({ items: [aSearchResult({ name: "Stale bracket" })] })));
    });
    expect(screen.queryByText("Stale bracket")).toBeNull();
  });
  it("supports Spanish search controls", async () => {
    const user = userEvent.setup();
    searchBox({ locale: "es" });
    await user.type(screen.getByRole("searchbox", { name: "Buscar en la biblioteca" }), "soporte");
    expect(await screen.findByText("Coincidencias por palabras")).toBeVisible();
    expect(screen.getByRole("button", { name: "Ver todos los resultados" })).toBeVisible();
  });
  it("reports unavailable suggestions with a recovery action", async () => {
    const user = userEvent.setup();
    searchBox({ routes: { "GET /api/v1/search?": json({}, 503) } });
    await user.type(screen.getByRole("searchbox"), "bracket");
    expect(await screen.findByRole("alert")).toHaveTextContent("Suggestions could not load");
    expect(screen.getByRole("button", { name: "Show all results" })).toBeVisible();
  });
});
