import { test, expect } from "../helpers";
import type { InferenceModel, SearchSettingsRead } from "../../../src/types/search";

const API = `http://127.0.0.1:${process.env.PLAYWRIGHT_REAL_API_PORT ?? 8410}`;

test("builds a local index and submits a semantic search from the top bar", async ({
  page,
}, testInfo) => {
  const initial: SearchSettingsRead = await (
    await page.request.get(`${API}/api/v1/config/ai-search`)
  ).json();
  let documentId: string | undefined;
  const name = `Assembly guide ${Date.now()}`;
  try {
    await page.goto("/documents/new");
    await page.locator("input.font-semibold").fill(name);
    await page
      .getByPlaceholder(/Write markdown/)
      .fill("A clamp that holds a lamp on a bicycle handlebar. Fit the two halves with bolts.");
    await page.getByRole("button", { name: "Save", exact: true }).click();
    await expect(page).toHaveURL(/\/documents\/\d+$/);
    documentId = page.url().split("/").at(-1);
    await page.goto("/settings?section=ai-search");
    const form = page.getByRole("form", { name: "AI Search", exact: true });
    await form.getByRole("checkbox", { name: "Enable AI Search", exact: true }).check();
    await form.getByRole("checkbox", { name: "Allow local models", exact: true }).check();
    await form.getByRole("button", { name: "Save search settings" }).click();
    await expect(page.getByText("AI Search settings saved", { exact: true })).toBeVisible();
    const catalog: InferenceModel[] = await (
      await page.request.get(`${API}/api/v1/inference/models`)
    ).json();
    const model = catalog.find((entry) => entry.installed && entry.modality === "text");
    expect(model).toBeDefined();
    await page
      .getByRole("combobox", { name: "Model", exact: true })
      .selectOption(`local:${model!.id}`);
    await page.getByRole("button", { name: "Verify local model" }).click();
    await expect(page.getByText("Local model verified", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Estimate resources" }).click();
    await expect(page.getByRole("status").filter({ hasText: /passages · up to/ })).toBeVisible();
    for (const [label, width, height] of [
      ["desktop", 1280, 900],
      ["mobile", 390, 844],
    ] as const) {
      await page.setViewportSize({ width, height });
      await expect(page.getByRole("button", { name: "Build new index" })).toBeEnabled();
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
      ).toBe(true);
      await page.screenshot({ path: testInfo.outputPath(`settings-${label}.png`), fullPage: true });
    }
    await page.getByRole("button", { name: "Build new index" }).click();
    await expect(page.getByText("Serving search now").locator("..")).toContainText(model!.key, {
      timeout: 60000,
    });
    await page.goto("/");
    const requests: string[] = [];
    page.on("request", (request) => {
      if (request.url().includes("/api/v1/search?")) requests.push(request.url());
    });
    const box = page.getByRole("searchbox", { name: "Search library" });
    await expect(page.getByRole("button", { name: "Search with AI" })).toBeVisible();
    await box.fill("bike lamp attachment");
    await expect.poll(() => requests.length).toBeGreaterThan(0);
    expect(requests.every((url) => new URL(url).searchParams.get("mode") === "lexical")).toBe(true);
    await box.press("Enter");
    await expect(page).toHaveURL(/\/search\?q=bike\+lamp\+attachment/);
    const link = page.getByRole("link", { name, exact: true });
    await expect(link).toBeVisible();
    await expect(link.locator("xpath=ancestor::li").getByText("Related description")).toBeVisible();
    for (const [label, width, height] of [
      ["mobile", 390, 844],
      ["desktop", 1280, 900],
    ] as const) {
      await page.setViewportSize({ width, height });
      expect(
        await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
      ).toBe(true);
      await page.screenshot({ path: testInfo.outputPath(`results-${label}.png`), fullPage: true });
    }
    await link.click();
    await expect(page).toHaveURL(new RegExp(`/documents/${documentId}$`));
  } finally {
    await page.request.put(`${API}/api/v1/config/ai-search`, { data: initial.settings });
    if (documentId) await page.request.delete(`${API}/api/v1/documents/${documentId}`);
  }
});
