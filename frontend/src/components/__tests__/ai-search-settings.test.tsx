import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AiSearchSettings } from "@/components/ai-search-settings";
import { anIngestJob } from "@/test-support/factories";
import { json, renderApp, type RenderAppOptions } from "@/test-support/render";
import {
  anInferenceEndpoint,
  anInferenceModel,
  aSearchGeneration,
  searchConfiguration,
  searchSettings,
} from "@/test-support/search";

function settingsPanel(options: RenderAppOptions = {}) {
  return renderApp(<AiSearchSettings />, {
    ...options,
    routes: {
      "GET /api/v1/config/ai-search": json(
        searchConfiguration({
          settings: searchSettings({
            enabled: true,
            local_models_enabled: true,
            download_enabled: true,
          }),
          endpoints: [anInferenceEndpoint()],
        }),
      ),
      "GET /api/v1/config/ai-search/generations": json([aSearchGeneration()]),
      "GET /api/v1/inference/models": json([anInferenceModel()]),
      "GET /api/v1/ingest/jobs": json([]),
      "PUT /api/v1/config/ai-search": json(searchConfiguration()),
      ...options.routes,
    },
  });
}
afterEach(() => vi.unstubAllGlobals());

describe("AI Search settings", () => {
  it("builds a visual profile independently while a text generation is building", async () => {
    const user = userEvent.setup();
    const clip = anInferenceModel({
      id: "d".repeat(64),
      key: "clip-vit-base-patch32-fp32",
      modality: "text_image",
      native_dimension: 512,
    });
    const app = settingsPanel({
      routes: {
        "GET /api/v1/inference/models": json([anInferenceModel(), clip]),
        "GET /api/v1/config/ai-search/generations": json([
          aSearchGeneration({ state: "building", phase: "backfill" }),
        ]),
        "POST /api/v1/config/ai-search/generations": json(
          aSearchGeneration({ profile: "multiview", model: clip.key, state: "building" }),
        ),
      },
    });
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Search index" }),
      "multiview",
    );
    await user.selectOptions(screen.getByRole("combobox", { name: "Model" }), `local:${clip.id}`);
    expect(screen.queryByRole("option", { name: /bge-small/ })).toBeNull();
    expect(
      within(screen.getByRole("combobox", { name: "Model" })).queryByRole("option", {
        name: /server-encoder/,
      }),
    ).toBeNull();
    await user.selectOptions(screen.getByRole("combobox", { name: "Combine views" }), "max");
    await user.click(screen.getByRole("button", { name: "Build new index" }));
    await waitFor(() => expect(app.requestsWithMethod("POST")).toHaveLength(1));
    expect(JSON.parse(app.requestsWithMethod("POST")[0].body)).toMatchObject({
      local_model_id: clip.id,
      profile: "multiview",
      aggregation: "max",
    });
    expect(JSON.parse(app.requestsWithMethod("POST")[0].body)).not.toHaveProperty("query_prefix");
  });
  it("refreshes installed models when a download completes", async () => {
    const user = userEvent.setup();
    const job = anIngestJob({ job_id: "download-2", kind: "model_download", state: "running" });
    const app = settingsPanel({
      routes: {
        "GET /api/v1/inference/models": json([anInferenceModel({ installed: false })]),
        "GET /api/v1/ingest/jobs": json([job]),
      },
    });
    await screen.findByRole("option", { name: /bge-small-en-v1.5/ });
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Model" }),
      `local:${"a".repeat(64)}`,
    );
    expect(screen.getByRole("button", { name: "Build new index" })).toBeDisabled();
    app.route({
      "GET /api/v1/inference/models": json([anInferenceModel()]),
      "GET /api/v1/ingest/jobs": json([{ ...job, state: "completed" }]),
    });
    await act(async () => {
      await app.client.refetchQueries({ queryKey: ["ai-search", "downloads"] });
    });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Build new index" })).toBeEnabled(),
    );
  });
  it("saves advanced ranking choices explicitly", async () => {
    const user = userEvent.setup();
    const app = settingsPanel();
    await user.click(await screen.findByText("Advanced settings"));
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Keyword search backend" }),
      "ranked_like",
    );
    const weight = screen.getByRole("spinbutton", { name: "Keyword ranking weight" });
    await user.clear(weight);
    await user.type(weight, "2");
    await user.click(screen.getByRole("button", { name: "Save search settings" }));
    await waitFor(() => expect(app.requestsWithMethod("PUT")).toHaveLength(1));
    expect(JSON.parse(app.requestsWithMethod("PUT")[0].body)).toMatchObject({
      lexical_backend: "ranked_like",
      lexical_weight: 2,
      semantic_weight: 1,
      rrf_k: 60,
    });
  });
  it("requires chat capability and render consent before enabling captions", async () => {
    const user = userEvent.setup();
    settingsPanel({
      routes: {
        "GET /api/v1/config/ai-search": json(
          searchConfiguration({
            endpoints: [
              anInferenceEndpoint({ kind: "chat", supports_images: true, native_dimension: null }),
            ],
          }),
        ),
      },
    });
    await user.click(await screen.findByText("Advanced settings"));
    const captions = screen.getByRole("checkbox", { name: "Enable generated descriptions" });
    expect(captions).toBeDisabled();
    await user.selectOptions(screen.getByRole("combobox", { name: "Chat and descriptions" }), "2");
    expect(captions).toBeDisabled();
    await user.click(
      screen.getByRole("checkbox", {
        name: "Allow rendered previews to be sent to the caption server",
      }),
    );
    expect(captions).toBeEnabled();
    await user.click(captions);
    await user.click(
      screen.getByRole("checkbox", {
        name: "Allow rendered previews to be sent to the caption server",
      }),
    );
    expect(captions).not.toBeChecked();
    expect(captions).toBeDisabled();
  });
  it("saves independent opt-ins without submitting endpoint secrets", async () => {
    const user = userEvent.setup();
    const app = settingsPanel();
    await user.click(await screen.findByRole("checkbox", { name: "Enable AI Search" }));
    await user.click(screen.getByRole("button", { name: "Save search settings" }));
    await waitFor(() => expect(app.requestsWithMethod("PUT")).toHaveLength(1));
    expect(JSON.parse(app.requestsWithMethod("PUT")[0].body)).toMatchObject({
      enabled: false,
      local_models_enabled: true,
    });
    expect(app.requestsWithMethod("PUT")[0].body).not.toContain("api_key");
  });
  it("separates pending model selection from the serving index", async () => {
    const user = userEvent.setup();
    settingsPanel();
    await screen.findByRole("option", { name: /bge-small-en-v1.5/ });
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Model" }),
      `local:${"a".repeat(64)}`,
    );
    expect(screen.getByText("Serving search now").parentElement).toHaveTextContent("old-encoder");
    expect(screen.getByText(/These choices are pending/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Build new index" })).toBeEnabled();
  });
  it("shows pinned provenance with a current-library estimate", async () => {
    const user = userEvent.setup();
    const app = settingsPanel({
      routes: {
        "POST /api/v1/config/ai-search/generations/estimate": json({
          passages: 24,
          estimated_bytes: 2097152,
          existing_bytes: 1048576,
          budget_bytes: 2147483648,
          fits_budget: true,
          estimated_seconds: 120,
        }),
      },
    });
    await screen.findByRole("option", { name: /bge-small-en-v1.5/ });
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Model" }),
      `local:${"a".repeat(64)}`,
    );
    expect(screen.getByText("MIT")).toBeVisible();
    expect(screen.getByText("en")).toBeVisible();
    expect(screen.getByText(/BAAI\/bge-small-en-v1.5@5c38/)).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Estimate resources" }));
    expect(await screen.findByText(/24 passages/)).toBeVisible();
    expect(app.requestsWithMethod("POST")).toHaveLength(1);
    expect(app.requestsWithMethod("POST")[0].url).toContain("/estimate");
  });
  it("starts a new index without replacing the serving label", async () => {
    const user = userEvent.setup();
    const app = settingsPanel({
      routes: {
        "POST /api/v1/config/ai-search/generations": json(
          aSearchGeneration({ id: 2, state: "building", phase: "reconcile" }),
        ),
      },
    });
    await screen.findByRole("option", { name: /bge-small-en-v1.5/ });
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Model" }),
      `local:${"a".repeat(64)}`,
    );
    await user.click(screen.getByRole("button", { name: "Build new index" }));
    await waitFor(() => expect(app.requestsWithMethod("POST")).toHaveLength(1));
    expect(JSON.parse(app.requestsWithMethod("POST")[0].body)).toMatchObject({
      local_model_id: "a".repeat(64),
      auto_activate: true,
      quantization: "float32",
    });
    expect(screen.getByText("Serving search now").parentElement).toHaveTextContent("old-encoder");
  });
  it("requires an explicit download request", async () => {
    const user = userEvent.setup();
    const app = settingsPanel({
      routes: {
        "GET /api/v1/inference/models": json([anInferenceModel({ installed: false })]),
        "POST /api/v1/inference/models/bge-small-en-v1.5/download": json({ job_id: "download-1" }),
      },
    });
    await screen.findByRole("option", { name: /bge-small-en-v1.5/ });
    await user.selectOptions(
      await screen.findByRole("combobox", { name: "Model" }),
      `local:${"a".repeat(64)}`,
    );
    expect(app.requestsWithMethod("POST")).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Build new index" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Download model" }));
    await waitFor(() =>
      expect(app.requestsWithMethod("POST")[0]?.url).toBe(
        "/api/v1/inference/models/bge-small-en-v1.5/download",
      ),
    );
  });
  it("displays cancellable download progress", async () => {
    const user = userEvent.setup();
    const app = settingsPanel({
      routes: {
        "GET /api/v1/ingest/jobs": json([
          anIngestJob({
            job_id: "download-1",
            kind: "model_download",
            state: "running",
            progress: 42,
            processed: 42000,
            total: 100000,
          }),
        ]),
        "POST /api/v1/inference/models/downloads/download-1/cancel": json(null, 204),
      },
    });
    expect(
      await screen.findByRole("progressbar", { name: "Model download progress" }),
    ).toHaveAttribute("value", "42");
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() =>
      expect(app.requestsWithMethod("POST")[0]?.url).toContain("download-1/cancel"),
    );
  });
  it.each(["cancel", "activate", "retry"] as const)(
    "sends a version-fenced %s action",
    async (action) => {
      const generation = aSearchGeneration({
        state: "building",
        phase: action === "activate" ? "ready" : "backfill",
        quarantined: action === "retry" ? 1 : 0,
      });
      const user = userEvent.setup();
      const app = settingsPanel({
        routes: {
          "GET /api/v1/config/ai-search/generations": json([generation]),
          [`POST /api/v1/config/ai-search/generations/1/${action}`]: json(generation),
        },
      });
      const label = { cancel: "Cancel", activate: "Activate index", retry: "Retry" }[action];
      await user.click(await screen.findByRole("button", { name: label }));
      await waitFor(() => expect(app.requestsWithMethod("POST")).toHaveLength(1));
      expect(JSON.parse(app.requestsWithMethod("POST")[0].body)).toEqual({
        version_token: "a".repeat(32),
      });
    },
  );
  it("keeps saved credentials out of an unrelated endpoint edit", async () => {
    const user = userEvent.setup();
    const app = settingsPanel({
      routes: {
        "POST /api/v1/config/ai-search/endpoints": json(
          anInferenceEndpoint({ id: 3, model: "replacement" }),
        ),
      },
    });
    await user.click(await screen.findByText("Compatible servers", { selector: "summary" }));
    await user.selectOptions(screen.getByRole("combobox", { name: "Server configuration" }), "2");
    const form = screen.getByRole("form", { name: "Inference server" });
    expect(within(form).getByLabelText("API key (optional)")).toHaveValue("");
    expect(within(form).getByText(/Credentials are configured/)).toBeVisible();
    await user.clear(within(form).getByRole("textbox", { name: "Model" }));
    await user.type(within(form).getByRole("textbox", { name: "Model" }), "replacement");
    await user.click(within(form).getByRole("button", { name: "Test and save server" }));
    await waitFor(() => expect(app.requestsWithMethod("POST")).toHaveLength(1));
    const proposal = JSON.parse(app.requestsWithMethod("POST")[0].body);
    expect(proposal).toMatchObject({ model: "replacement", inherit_credentials_from_id: 2 });
    expect(proposal).not.toHaveProperty("api_key");
    expect(proposal).not.toHaveProperty("headers");
  });
  it("requires explicit replacement of authentication headers", async () => {
    const user = userEvent.setup();
    const app = settingsPanel({
      routes: { "POST /api/v1/config/ai-search/endpoints": json(anInferenceEndpoint({ id: 3 })) },
    });
    await user.click(await screen.findByText("Compatible servers", { selector: "summary" }));
    await user.selectOptions(screen.getByRole("combobox", { name: "Server configuration" }), "2");
    await user.click(screen.getByText("Custom authentication headers", { selector: "summary" }));
    await user.click(screen.getByRole("checkbox", { name: "Replace saved headers" }));
    await user.click(screen.getByRole("button", { name: "Add header" }));
    await user.type(screen.getByLabelText("Header name 1"), "X-New-Key");
    await user.type(screen.getByLabelText("Header value 1"), "test-only-key");
    await user.click(screen.getByRole("button", { name: "Test and save server" }));
    await waitFor(() => expect(app.requestsWithMethod("POST")).toHaveLength(1));
    expect(JSON.parse(app.requestsWithMethod("POST")[0].body).headers).toEqual({
      "X-New-Key": "test-only-key",
    });
  });
  it("supports Spanish maintenance controls", async () => {
    settingsPanel({ locale: "es" });
    expect(
      await screen.findByRole("button", { name: "Guardar ajustes de búsqueda" }),
    ).toBeVisible();
    expect(screen.getByText("Preparar un índice nuevo")).toBeVisible();
  });
  it("reports a settings load failure with retry", async () => {
    settingsPanel({ routes: { "GET /api/v1/config/ai-search": json({}, 503) } });
    expect(await screen.findByText("AI Search settings could not load")).toBeVisible();
    expect(screen.getByRole("button", { name: "Retry" })).toBeVisible();
  });
});
