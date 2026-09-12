import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";

import { InferenceEndpointForm } from "@/components/inference-endpoint-form";
import { SearchGenerationControls } from "@/components/search-generation-controls";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { getSearchSettings, importEnvironmentEndpoint, saveSearchSettings } from "@/lib/api/search";
import { useI18n } from "@/lib/i18n";
import { toast } from "@/lib/toast";
import type { SearchSettingsRead } from "@/types/search";

function SettingsForm({ initial, onSaved }: { initial: SearchSettingsRead; onSaved: () => void }) {
  const { t } = useI18n();
  const [draft, setDraft] = useState(initial.settings);
  const chat = initial.endpoints.find(
    (endpoint) => endpoint.id === draft.chat_endpoint_id && endpoint.kind === "chat",
  );
  const save = useMutation({
    mutationFn: () => saveSearchSettings(draft),
    onSuccess: () => {
      toast.success(t("aiSearch.settingsSaved"));
      onSaved();
    },
    onError: toast.error,
  });
  const toggles = [
    ["enabled", "aiSearch.enable"],
    ["local_models_enabled", "aiSearch.enableLocal"],
    ["download_enabled", "aiSearch.allowDownloads"],
  ] as const;
  return (
    <form
      className="space-y-4 p-4 sm:p-5"
      aria-label={t("aiSearch.settingsTitle")}
      onSubmit={(event) => {
        event.preventDefault();
        save.mutate();
      }}
    >
      <div className="space-y-3">
        {toggles.map(([field, label]) => (
          <label key={field} className="flex items-center gap-2 text-sm">
            <Checkbox
              ariaLabel={t(label)}
              checked={draft[field]}
              onChange={(value) => setDraft({ ...draft, [field]: value })}
            />
            {t(label)}
          </label>
        ))}
      </div>
      <p className="max-w-prose text-xs leading-relaxed text-muted-foreground">
        {t("aiSearch.localHelp")}
      </p>
      <details className="border-t border-border pt-3">
        <summary className="cursor-pointer text-sm font-medium">{t("aiSearch.advanced")}</summary>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <label className="space-y-1 text-sm">
            {t("aiSearch.lexicalBackend")}
            <select
              className="block w-full rounded-md border border-input bg-background p-2"
              value={draft.lexical_backend}
              onChange={(event) =>
                setDraft({
                  ...draft,
                  lexical_backend: event.target.value === "ranked_like" ? "ranked_like" : "auto",
                })
              }
            >
              <option value="auto">{t("aiSearch.automatic")}</option>
              <option value="ranked_like">{t("aiSearch.rankedLike")}</option>
            </select>
          </label>
          {(
            [
              ["lexical_weight", "aiSearch.lexicalWeight", 0.01, 10, 0.01],
              ["semantic_weight", "aiSearch.semanticWeight", 0.01, 10, 0.01],
              ["rrf_k", "aiSearch.rankSmoothing", 1, 1000, 1],
            ] as const
          ).map(([field, label, min, max, step]) => (
            <label key={field} className="space-y-1 text-sm">
              {t(label)}
              <Input
                type="number"
                required
                min={min}
                max={max}
                step={step}
                value={draft[field]}
                onChange={(event) => setDraft({ ...draft, [field]: Number(event.target.value) })}
              />
            </label>
          ))}
          <label className="space-y-1 text-sm">
            {t("aiSearch.indexBudget")}
            <Input
              type="number"
              required
              min={1}
              max={1048576}
              value={draft.max_index_bytes / 1048576}
              onChange={(event) =>
                setDraft({ ...draft, max_index_bytes: Number(event.target.value) * 1048576 })
              }
            />
          </label>
          <label className="space-y-1 text-sm">
            {t("aiSearch.retention")}
            <Input
              type="number"
              required
              min={1}
              max={720}
              value={draft.rollback_retention_hours}
              onChange={(event) =>
                setDraft({ ...draft, rollback_retention_hours: Number(event.target.value) })
              }
            />
          </label>
          <label className="space-y-1 text-sm">
            {t("aiSearch.queryTimeout")}
            <Input
              type="number"
              required
              min={0.05}
              max={30}
              step={0.05}
              value={draft.query_timeout_seconds}
              onChange={(event) =>
                setDraft({ ...draft, query_timeout_seconds: Number(event.target.value) })
              }
            />
          </label>
          <label className="space-y-1 text-sm">
            {t("aiSearch.semanticFloor")}
            <Input
              type="number"
              required
              min={-1}
              max={1}
              step={0.01}
              value={draft.semantic_floor}
              onChange={(event) =>
                setDraft({ ...draft, semantic_floor: Number(event.target.value) })
              }
            />
          </label>
        </div>
        <label className="mt-3 block space-y-1 text-sm">
          {t("aiSearch.chatEndpoint")}
          <select
            className="block w-full rounded-md border border-input bg-background p-2"
            value={draft.chat_endpoint_id ?? ""}
            onChange={(event) => {
              const endpoint = initial.endpoints.find(
                (item) => item.id === Number(event.target.value),
              );
              setDraft({
                ...draft,
                chat_endpoint_id: event.target.value ? Number(event.target.value) : null,
                captions_enabled: draft.captions_enabled && !!endpoint?.supports_images,
                nl_filters_enabled: draft.nl_filters_enabled && !!endpoint,
              });
            }}
          >
            <option value="">{t("aiSearch.none")}</option>
            {initial.endpoints
              .filter((endpoint) => endpoint.kind === "chat")
              .map((endpoint) => (
                <option key={endpoint.id} value={endpoint.id}>
                  {endpoint.model} · {endpoint.host}
                </option>
              ))}
          </select>
        </label>
        <div className="mt-3 space-y-2">
          {(
            [
              ["send_rendered_images", "aiSearch.sendRenderedImages"],
              ["send_query_images", "aiSearch.sendQueryImages"],
              ["captions_enabled", "aiSearch.enableCaptions"],
              ["nl_filters_enabled", "aiSearch.enableNl"],
            ] as const
          ).map(([field, label]) => (
            <label key={field} className="flex items-center gap-2 text-sm">
              <Checkbox
                ariaLabel={t(label)}
                checked={draft[field]}
                disabled={
                  field === "captions_enabled"
                    ? !chat?.supports_images || !draft.send_rendered_images
                    : field === "nl_filters_enabled" && !chat
                }
                onChange={(value) =>
                  setDraft({
                    ...draft,
                    [field]: value,
                    captions_enabled:
                      field === "send_rendered_images" && !value
                        ? false
                        : field === "captions_enabled"
                          ? value
                          : draft.captions_enabled,
                  })
                }
              />
              {t(label)}
            </label>
          ))}
        </div>
        <p className="mt-2 text-xs text-muted-foreground">{t("aiSearch.captionRequirements")}</p>
      </details>
      {save.isError && (
        <p role="alert" className="text-sm text-destructive">
          {t("aiSearch.settingsError")}
        </p>
      )}
      <Button type="submit" loading={save.isPending}>
        {t("aiSearch.saveSettings")}
      </Button>
    </form>
  );
}

export function AiSearchSettings() {
  const { t } = useI18n();
  const [editing, setEditing] = useState<number | null>(null);
  const settings = useQuery({ queryKey: ["ai-search", "settings"], queryFn: getSearchSettings });
  const refresh = () => {
    void settings.refetch();
  };
  const fromEnvironment = useMutation({
    mutationFn: importEnvironmentEndpoint,
    onSuccess: refresh,
    onError: toast.error,
  });
  return (
    <Card className="overflow-hidden">
      <div className="flex items-start gap-3 border-b border-border px-4 py-4 sm:px-5">
        <Search className="h-8 w-8 shrink-0 rounded-md bg-muted p-1.5" aria-hidden />
        <div>
          <h3 className="text-sm font-semibold">{t("aiSearch.settingsTitle")}</h3>
          <p className="mt-1 max-w-prose text-xs text-muted-foreground">
            {t("aiSearch.settingsIntro")}
          </p>
        </div>
      </div>
      {settings.isError ? (
        <EmptyState
          title={t("aiSearch.settingsLoadError")}
          action={<Button onClick={refresh}>{t("aiSearch.retry")}</Button>}
        />
      ) : !settings.data ? (
        <p role="status" className="p-5 text-sm">
          {t("aiSearch.loading")}
        </p>
      ) : (
        <>
          <SettingsForm
            key={JSON.stringify(settings.data.settings)}
            initial={settings.data}
            onSaved={refresh}
          />
          <SearchGenerationControls settings={settings.data} />
          <details className="border-t border-border p-4 sm:p-5">
            <summary className="cursor-pointer text-sm font-semibold">
              {t("aiSearch.endpoints")}
            </summary>
            <div className="mt-4 space-y-4">
              <label className="block space-y-1 text-sm">
                {t("aiSearch.editEndpoint")}
                <select
                  className="block w-full rounded-md border border-input bg-background p-2"
                  value={editing ?? ""}
                  onChange={(event) =>
                    setEditing(event.target.value ? Number(event.target.value) : null)
                  }
                >
                  <option value="">{t("aiSearch.newEndpoint")}</option>
                  {settings.data.endpoints.map((endpoint) => (
                    <option key={endpoint.id} value={endpoint.id}>
                      {endpoint.model} · {endpoint.host}
                    </option>
                  ))}
                </select>
              </label>
              <InferenceEndpointForm
                key={editing ?? "new"}
                initial={settings.data.endpoints.find((endpoint) => endpoint.id === editing)}
                onSaved={() => {
                  setEditing(null);
                  refresh();
                }}
              />
              {settings.data.environment_endpoints.map((kind) => (
                <Button
                  key={kind}
                  variant="outline"
                  loading={fromEnvironment.isPending}
                  onClick={() => fromEnvironment.mutate(kind)}
                >
                  {t(
                    kind === "embedding"
                      ? "aiSearch.importEmbeddingEnvironment"
                      : "aiSearch.importChatEnvironment",
                  )}
                </Button>
              ))}
            </div>
          </details>
        </>
      )}
    </Card>
  );
}
