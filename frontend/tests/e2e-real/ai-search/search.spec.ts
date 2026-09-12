import { test, expect } from "../helpers";
import { modelCard, uploadModel } from "../util";
import { readFileSync } from "node:fs";
import type { InferenceModel, SearchSettingsRead } from "../../../src/types/search";
import type { ModelRead } from "../../../src/types/models";

const API = `http://127.0.0.1:${process.env.PLAYWRIGHT_REAL_API_PORT ?? 8410}`;

test("searches an image and reuses a Model through local visual indexes", async ({
  page,
}, testInfo) => {
  test.setTimeout(180000);
  const initial: SearchSettingsRead = await (
    await page.request.get(`${API}/api/v1/config/ai-search`)
  ).json();
  const ids: number[] = [];
  const names = [`Visual source ${Date.now()}`, `Visual relative ${Date.now()}`];
  try {
    for (const name of names) {
      const mesh = readFileSync(
        new URL("../../../../testdata/Calibration Cube.stl", import.meta.url),
      );
      // Binary STL's 80-byte header does not change geometry, but avoids ingest deduplication.
      mesh.write(name, 0, "utf8");
      await uploadModel(page, name, {
        gcode: false,
        meshFile: { name: `${name}.stl`, mimeType: "model/stl", buffer: mesh },
      });
      const href = await modelCard(page, name).getAttribute("href");
      expect(href).toMatch(/\/models\/\d+$/);
      ids.push(Number(href!.split("/").at(-1)));
    }
    const source: ModelRead = await (
      await page.request.get(`${API}/api/v1/models/${ids[0]}`)
    ).json();
    const thumbnail = source.thumbnail_url;
    expect(thumbnail).toBeTruthy();
    const thumbnailResponse = await page.request.get(new URL(thumbnail!, API).href);
    const queryImage = await thumbnailResponse.body();
    const mimeType = thumbnailResponse.headers()["content-type"].split(";")[0];
    await page.goto("/settings?section=ai-search");
    const form = page.getByRole("form", { name: "AI Search", exact: true });
    await form.getByRole("checkbox", { name: "Enable AI Search", exact: true }).check();
    await form.getByRole("checkbox", { name: "Allow local models", exact: true }).check();
    await form.getByRole("button", { name: "Save search settings" }).click();
    await expect(page.getByText("AI Search settings saved", { exact: true })).toBeVisible();
    const catalog: InferenceModel[] = await (
      await page.request.get(`${API}/api/v1/inference/models`)
    ).json();
    const model = catalog.find((entry) => entry.installed && entry.modality === "text_image");
    expect(model).toBeDefined();
    await page.getByRole("combobox", { name: "Search index" }).selectOption("multiview");
    await page
      .getByRole("combobox", { name: "Model", exact: true })
      .selectOption(`local:${model!.id}`);
    await page.getByRole("button", { name: "Build new index" }).click();
    await expect
      .poll(
        async () => (await (await page.request.get(`${API}/api/v1/search/status`)).json()).legs,
        { timeout: 90000 },
      )
      .toEqual(expect.arrayContaining(["thumbnail", "multiview"]));
    await page.goto("/");
    await page.getByRole("button", { name: "Search by image" }).click();
    await expect(page).toHaveURL(/\/search\?image=1$/);
    await page
      .locator('input[type="file"][aria-label="Choose image"]')
      .setInputFiles({ name: "private-query", mimeType, buffer: queryImage });
    const result = page.getByRole("link", { name: names[0], exact: true });
    await expect(result).toBeVisible();
    await expect(
      result.locator("xpath=ancestor::li").getByText("Shape match", { exact: true }),
    ).toBeVisible();
    expect(page.url()).not.toContain("private-query");
    for (const [label, width, height] of [
      ["desktop", 1280, 900],
      ["mobile", 390, 844],
    ] as const) {
      await page.setViewportSize({ width, height });
      expect(
        await page
          .getByText("Your image is processed locally for this search and is not saved.")
          .evaluate((element) => element.clientWidth),
      ).toBeGreaterThan(180);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      );
      await page.screenshot({ path: testInfo.outputPath(`visual-${label}.png`), fullPage: true });
    }
    await page.getByRole("button", { name: "Clear image" }).click();
    await expect(result).toHaveCount(0);
    await expect(page.getByRole("img", { name: "Image used for this search" })).toHaveCount(0);
    await page.goto(`/models/${ids[0]}`);
    await page.getByRole("button", { name: "Model actions" }).click();
    await page.getByRole("menuitem", { name: "Find related Models" }).click();
    await expect(page.getByRole("link", { name: names[1], exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: names[0], exact: true })).toHaveCount(0);
  } finally {
    await page.request.put(`${API}/api/v1/config/ai-search`, { data: initial.settings });
    for (const id of ids) await page.request.delete(`${API}/api/v1/models/${id}`);
  }
});

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

test("builds the optional local point profile for geometry search", async ({ page }, testInfo) => {
  test.setTimeout(180000);
  const initial: SearchSettingsRead = await (
    await page.request.get(`${API}/api/v1/config/ai-search`)
  ).json();
  let modelId: number | undefined;
  const name = `Geometry source ${Date.now()}`;
  try {
    const mesh = readFileSync(
      new URL("../../../../testdata/Calibration Cube.stl", import.meta.url),
    );
    mesh.write(name, 0, "utf8");
    await uploadModel(page, name, {
      gcode: false,
      meshFile: { name: `${name}.stl`, mimeType: "model/stl", buffer: mesh },
    });
    modelId = Number((await modelCard(page, name).getAttribute("href"))!.split("/").at(-1));
    await page.goto("/settings?section=ai-search");
    const form = page.getByRole("form", { name: "AI Search", exact: true });
    await form.getByRole("checkbox", { name: "Enable AI Search", exact: true }).check();
    await form.getByRole("checkbox", { name: "Allow local models", exact: true }).check();
    await form.getByRole("button", { name: "Save search settings" }).click();
    await expect(page.getByText("AI Search settings saved", { exact: true })).toBeVisible();
    const catalog: InferenceModel[] = await (
      await page.request.get(`${API}/api/v1/inference/models`)
    ).json();
    const clip = catalog.find((entry) => entry.installed && entry.modality === "text_image");
    const point =
      catalog.find(
        (entry) =>
          entry.installed && entry.modality === "point_cloud" && entry.key !== "point-contract",
      ) ?? catalog.find((entry) => entry.installed && entry.modality === "point_cloud");
    expect(clip).toBeDefined();
    expect(point).toBeDefined();
    await page.getByRole("combobox", { name: "Search index" }).selectOption("thumbnail");
    await page
      .getByRole("combobox", { name: "Model", exact: true })
      .selectOption(`local:${clip!.id}`);
    await page.getByRole("button", { name: "Build new index" }).click();
    await expect
      .poll(
        async () => (await (await page.request.get(`${API}/api/v1/search/status`)).json()).legs,
        { timeout: 90000 },
      )
      .toContain("thumbnail");
    await page.getByRole("combobox", { name: "Search index" }).selectOption("point_cloud");
    await page
      .getByRole("combobox", { name: "Model", exact: true })
      .selectOption(`local:${point!.id}`);
    await page.getByRole("button", { name: "Build new index" }).click();
    await expect
      .poll(
        async () => (await (await page.request.get(`${API}/api/v1/search/status`)).json()).legs,
        { timeout: 90000 },
      )
      .toContain("point_cloud");
    await page.goto("/search?q=a+cube");
    const link = page.getByRole("link", { name, exact: true });
    await expect(link).toBeVisible();
    await expect(
      link.locator("xpath=ancestor::li").getByText("Shape match", { exact: true }),
    ).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath("point-search.png"), fullPage: true });
  } finally {
    await page.request.put(`${API}/api/v1/config/ai-search`, { data: initial.settings });
    if (modelId) await page.request.delete(`${API}/api/v1/models/${modelId}`);
  }
});
