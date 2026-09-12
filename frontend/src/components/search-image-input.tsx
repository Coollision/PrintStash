import { useEffect, useRef, useState } from "react";
import { ImagePlus, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useI18n } from "@/lib/i18n";

export function SearchImageInput({
  image,
  enabled,
  onChange,
}: {
  image: File | null;
  enabled: boolean;
  onChange: (image: File | null) => void;
}) {
  const { t } = useI18n();
  const input = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<{ file: File; url: string } | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    return () => {
      if (preview) URL.revokeObjectURL(preview.url);
    };
  }, [preview]);
  return (
    <div className="mb-5 rounded-lg border border-border bg-muted/30 p-4">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
        <div className="flex min-w-0 flex-1 items-start gap-3">
          {preview?.file === image && (
            <img
              src={preview.url}
              alt={t("aiSearch.queryImage")}
              className="h-20 w-20 shrink-0 rounded-md border border-border bg-background object-contain"
            />
          )}
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium">{t("aiSearch.imagePrompt")}</p>
            <p className="mt-1 max-w-prose text-xs leading-relaxed text-muted-foreground">
              {t("aiSearch.imagePrivacy")}
            </p>
            <p className="mt-1 text-xs text-muted-foreground">{t("aiSearch.imageLimits")}</p>
          </div>
        </div>
        <input
          ref={input}
          type="file"
          className="sr-only"
          accept="image/png,image/jpeg,image/webp"
          aria-label={t("aiSearch.chooseImage")}
          disabled={!enabled}
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (!file) return;
            if (
              !file.size ||
              file.size > 8 * 1024 * 1024 ||
              !["image/png", "image/jpeg", "image/webp"].includes(file.type)
            ) {
              setError(true);
              return;
            }
            setError(false);
            setPreview({ file, url: URL.createObjectURL(file) });
            onChange(file);
          }}
        />
        <div className="flex shrink-0 items-center gap-2">
          <Button variant="outline" disabled={!enabled} onClick={() => input.current?.click()}>
            <ImagePlus className="mr-2 h-4 w-4" />
            {t("aiSearch.chooseImage")}
          </Button>
          {image && (
            <Button
              variant="ghost"
              size="icon"
              aria-label={t("aiSearch.clearImage")}
              onClick={() => {
                onChange(null);
                setPreview(null);
                setError(false);
              }}
            >
              <X className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>
      {!enabled && (
        <p role="status" className="mt-3 text-sm text-muted-foreground">
          {t("aiSearch.visualUnavailable")}
        </p>
      )}
      {error && (
        <p role="alert" className="mt-3 text-sm text-destructive">
          {t("aiSearch.invalidImage")}
        </p>
      )}
    </div>
  );
}
