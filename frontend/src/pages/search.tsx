import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { Search } from "lucide-react";

import { SearchEvidenceList } from "@/components/search-evidence";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageContainer } from "@/components/ui/page-container";
import { PageHeader } from "@/components/ui/page-header";
import { getSearchStatus, searchLibrary } from "@/lib/api/search";
import { useAuth } from "@/lib/auth-context";
import { ApiError } from "@/lib/errors";
import { useI18n } from "@/lib/i18n";
import { Link } from "@/lib/link";
import { useRouter, useSearchParams } from "@/lib/navigation";
import type { SearchSubjectType } from "@/types/search";

const subjectTypes: SearchSubjectType[] = ["model", "collection", "multipart_model", "document"];

export default function SearchPage() {
  const { t } = useI18n();
  const { user } = useAuth();
  const router = useRouter();
  const queryClient = useQueryClient();
  const params = useSearchParams();
  const q = params.get("q") ?? "";
  const mode = params.get("mode") === "lexical" ? "lexical" : "hybrid";
  const types = subjectTypes.filter((type) => params.getAll("type").includes(type));
  const status = useQuery({
    queryKey: ["ai-search", "status", user?.id],
    queryFn: getSearchStatus,
    enabled: !!user,
    refetchInterval: 15000,
  });
  const queryKey = ["search-results", user?.id, q, mode, types];
  const results = useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam, signal }: { pageParam: string | undefined; signal: AbortSignal }) =>
      searchLibrary(
        { q, mode, cursor: pageParam, types: types.length ? types : undefined },
        signal,
      ),
    initialPageParam: undefined,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    enabled: !!user && !!q.trim(),
    retry: false,
    gcTime: 0,
  });
  function changeType(type: SearchSubjectType) {
    const next = types.includes(type) ? types.filter((item) => item !== type) : [...types, type];
    const query = new URLSearchParams(params);
    query.delete("type");
    next.forEach((item) => query.append("type", item));
    router.push(`/search?${query}`);
  }
  const pages = results.data?.pages ?? [];
  const first = pages[0];
  const items = pages.flatMap((page) => page.items);
  const cursorExpired =
    results.error instanceof ApiError && results.error.code === "search_cursor_expired";
  return (
    <PageContainer>
      <PageHeader
        title={t("aiSearch.resultsTitle")}
        description={q ? t("aiSearch.resultsFor", { query: q }) : t("aiSearch.startSearch")}
      />
      <div
        className="mb-4 flex flex-wrap items-center gap-2"
        aria-label={t("aiSearch.resultTypes")}
      >
        {subjectTypes.map((type) => (
          <Button
            key={type}
            size="sm"
            variant={types.includes(type) ? "secondary" : "outline"}
            aria-pressed={types.includes(type)}
            onClick={() => changeType(type)}
          >
            {t(`aiSearch.type.${type}`)}
          </Button>
        ))}
        <label className="ml-auto flex items-center gap-2 text-sm">
          {t("aiSearch.searchMode")}
          <select
            aria-label={t("aiSearch.searchMode")}
            value={mode}
            className="rounded-md border border-input bg-background p-2 text-sm"
            onChange={(event) => {
              const next = new URLSearchParams(params);
              next.set("mode", event.target.value);
              router.push(`/search?${next}`);
            }}
          >
            <option value="hybrid">{t("aiSearch.hybrid")}</option>
            <option value="lexical">{t("aiSearch.keywordOnly")}</option>
          </select>
        </label>
      </div>
      {status.data?.remote_hosts.length ? (
        <p className="mb-3 text-sm text-muted-foreground">
          {t("aiSearch.remoteDisclosure", { hosts: status.data.remote_hosts.join(", ") })}
        </p>
      ) : null}
      {status.data?.backlog && (
        <p role="status" className="mb-3 text-sm text-muted-foreground">
          {t("aiSearch.backlog")}
        </p>
      )}
      {pages.some((page) => page.degraded.length) && (
        <p role="status" className="mb-3 rounded-md bg-warning/10 p-3 text-sm text-foreground">
          {t("aiSearch.degraded")}
        </p>
      )}
      {!q.trim() ? (
        <EmptyState icon={Search} title={t("aiSearch.startSearch")} />
      ) : results.isPending ? (
        <p role="status" className="py-8 text-sm text-muted-foreground">
          {t("aiSearch.searching")}
        </p>
      ) : results.isError && !items.length ? (
        <EmptyState
          title={t("aiSearch.loadError")}
          action={<Button onClick={() => void results.refetch()}>{t("aiSearch.retry")}</Button>}
        />
      ) : items.length ? (
        <Card className="overflow-hidden">
          <ul className="divide-y divide-border">
            {items.map((item) => (
              <li key={`${item.subject_type}:${item.subject_id}`} className="px-4 py-4 sm:px-5">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="min-w-0 break-words text-base font-semibold">
                    <Link
                      href={item.href}
                      className="rounded-sm hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    >
                      {item.name}
                    </Link>
                  </h2>
                  <Badge variant="outline">{t(`aiSearch.type.${item.subject_type}`)}</Badge>
                </div>
                <SearchEvidenceList evidence={item.evidence} />
              </li>
            ))}
          </ul>
        </Card>
      ) : (
        <EmptyState
          icon={Search}
          title={t(
            first?.outcome === "no_strong_matches"
              ? "aiSearch.noStrongMatches"
              : "aiSearch.noResults",
          )}
          description={t("aiSearch.tryAnotherQuery")}
        />
      )}
      {results.isFetchNextPageError && (
        <p role="alert" className="mt-4 text-sm text-destructive">
          {t(cursorExpired ? "aiSearch.cursorExpired" : "aiSearch.loadError")}
        </p>
      )}
      {cursorExpired ? (
        <Button
          className="mt-4"
          variant="outline"
          onClick={() => void queryClient.resetQueries({ queryKey, exact: true })}
        >
          {t("aiSearch.restartSearch")}
        </Button>
      ) : (
        results.hasNextPage && (
          <Button
            className="mt-4"
            variant="outline"
            loading={results.isFetchingNextPage}
            onClick={() => void results.fetchNextPage()}
          >
            {t("aiSearch.loadMore")}
          </Button>
        )
      )}
      {pages.some((page) => page.truncated) && (
        <p className="mt-4 text-xs text-muted-foreground">{t("aiSearch.boundedResults")}</p>
      )}
    </PageContainer>
  );
}
