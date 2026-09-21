"use client";

import { uiText } from "@/lib/locale";
import { useUiLocale } from "@/lib/i18n";

import { useState } from "react";
import { ChevronDown, ExternalLink } from "lucide-react";

import { getJson } from "@/lib/api/request";
import { toast } from "@/lib/toast";
import { DropdownMenu } from "@/components/ui/dropdown-menu";

type Slicer = {
  name: string;
  scheme: string;
  // File extensions this slicer can actually open from a URL.
  types: ReadonlySet<string>;
  // When set, open this http(s) template instead of a desktop URL scheme.
  // `{file}` is replaced with the URL-encoded file URL.
  urlTemplate?: string;
};

// Which file types each slicer opens from a URL. Bambu Studio only loads 3MF
// via URL (other formats error with "unknown format"); OrcaSlicer is broad.
// PrusaSlicer doesn't reliably open arbitrary self-hosted URLs yet
// (prusa3d/PrusaSlicer#13752) but is kept listed as best-effort.
const ORCA_TYPES = new Set(["stl", "3mf", "obj", "step", "gcode"]);
const DESKTOP_SLICERS: Slicer[] = [
  { name: "OrcaSlicer", scheme: "orcaslicer", types: ORCA_TYPES },
  { name: "Bambu Studio", scheme: "bambustudio", types: new Set(["3mf"]) },
  { name: "PrusaSlicer", scheme: "prusaslicer", types: ORCA_TYPES },
];

// An optional web-based slicer, configured at build time. Desktop slicers
// cannot be driven from the browser, so a self-hosted page is the only way to
// choose slicing options (material, colours, tool mapping) without leaving it.
const externalName = import.meta.env.VITE_EXTERNAL_SLICER_NAME as string | undefined;
const externalUrl = import.meta.env.VITE_EXTERNAL_SLICER_URL as string | undefined;
const externalTypes = import.meta.env.VITE_EXTERNAL_SLICER_TYPES as string | undefined;

const SLICERS: Slicer[] =
  externalName && externalUrl
    ? [
        ...DESKTOP_SLICERS,
        {
          name: externalName,
          scheme: "external",
          types: externalTypes
            ? new Set(
                externalTypes
                  .split(",")
                  .map((t: string) => t.trim().toLowerCase())
                  .filter(Boolean),
              )
            : ORCA_TYPES,
          urlTemplate: externalUrl,
        },
      ]
    : DESKTOP_SLICERS;

function isMacOS() {
  if (!("navigator" in globalThis)) return false;
  // navigator.platform is deprecated but still the most reliable signal here;
  // fall back to the user-agent string.
  const platform = navigator.platform ?? "";
  return /Mac/i.test(platform) || /Mac OS X/i.test(navigator.userAgent ?? "");
}

function slicerHref(slicer: Slicer, fileUrl: string) {
  if (slicer.urlTemplate) {
    return slicer.urlTemplate.replace("{file}", encodeURIComponent(fileUrl));
  }
  // Bambu Studio uses a different URL scheme on macOS: the file URL is
  // appended directly to the `bambustudioopen://` host instead of being passed
  // as an `open?file=` query parameter (issue #27).
  if (slicer.scheme === "bambustudio" && isMacOS()) {
    return `bambustudioopen://${encodeURIComponent(fileUrl)}`;
  }
  return `${slicer.scheme}://open?file=${encodeURIComponent(fileUrl)}`;
}

export function SlicerOpenButton({
  fileId,
  fileType,
  size = "md",
}: {
  fileId: number;
  fileType: string;
  size?: "sm" | "md";
}) {
  useUiLocale();
  const [open, setOpen] = useState(false);

  const iconSize = size === "sm" ? "h-3.5 w-3.5" : "h-4 w-4";
  const chevronSize = size === "sm" ? "h-2.5 w-2.5" : "h-3 w-3";

  const slicers = SLICERS.filter((s) => s.types.has(fileType));
  if (slicers.length === 0) return null;

  async function openInSlicer(slicer: Slicer) {
    setOpen(false);
    try {
      // The slicer is a separate process with no login session, so it can't
      // send our bearer token. The backend returns a short-lived, filename-
      // bearing download URL (the path carries the extension so the slicer can
      // detect the format) with a file-scoped token embedded.
      const { url } = await getJson<{ url: string }>(`/api/v1/files/${fileId}/slicer-url`, {
        fresh: true,
      });
      const fileUrl = `${window.location.origin}${url}`;
      window.location.assign(slicerHref(slicer, fileUrl));
    } catch {
      toast.error(uiText("Couldn't open in slicer"));
    }
  }

  return (
    <DropdownMenu
      open={open}
      onOpenChange={setOpen}
      align="end"
      role="menu"
      trigger={
        <button
          data-menu-trigger
          onClick={() => setOpen((o) => !o)}
          title={uiText("Open in slicer")}
          aria-haspopup="menu"
          aria-expanded={open}
          className="inline-flex items-center gap-0.5 text-on-surface-variant hover:text-primary p-2 rounded hover:bg-surface-container-high transition-colors"
        >
          <ExternalLink className={iconSize} />
          <ChevronDown className={chevronSize} />
        </button>
      }
      contentClassName="min-w-[10rem] rounded border border-outline-variant bg-surface shadow-lg"
    >
      <p className="px-3 py-1.5 font-mono text-3xs uppercase tracking-wider text-on-surface-variant border-b border-outline-variant">
        {uiText("Open in slicer")}
      </p>
      {slicers.map((slicer) => (
        <button
          key={slicer.scheme}
          type="button"
          role="menuitem"
          onClick={() => openInSlicer(slicer)}
          className="block w-full px-3 py-2 text-left font-mono text-xs text-on-surface hover:bg-surface-container-low focus-visible:bg-surface-container-low outline-none transition-colors last:rounded-b"
        >
          {slicer.name}
        </button>
      ))}
    </DropdownMenu>
  );
}
