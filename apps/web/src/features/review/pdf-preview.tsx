import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { pdfHref } from "./api";

/**
 * The PDF is loaded through the same-origin proxy (/api/runs/{id}/pdf), which
 * follows the signed redirect server side: no signed URL ever reaches the browser.
 */
export function PdfPreview({
  runId,
  which,
  ready,
  rev,
}: {
  runId: string;
  which: "latest" | "approved";
  ready: boolean;
  rev?: number | null;
}) {
  const href = pdfHref(runId, which, rev);
  return (
    <Card as="section" aria-labelledby="pdf-h" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="pdf-h" className="text-section font-semibold">
          {which === "approved" ? "Approved PDF" : "PDF preview"}
        </h2>
        {ready && (
          <a
            href={href}
            target="_blank"
            rel="noreferrer"
            className="text-body font-medium text-accent-text underline underline-offset-2"
          >
            Open PDF in a new tab
          </a>
        )}
      </div>
      <div role="status" aria-live="polite">
        {ready ? (
          <span className="sr-only">PDF ready</span>
        ) : (
          <p className="text-hint text-muted">
            Rendering the PDF with your latest edits…
          </p>
        )}
      </div>
      {ready ? (
        <iframe
          key={`${runId}-${rev ?? "x"}`}
          title="Resume PDF preview"
          src={href}
          className="h-[520px] w-full rounded-control border border-border bg-surface-2 md:h-[640px]"
        />
      ) : (
        <Skeleton className="h-[320px] w-full md:h-[640px]" />
      )}
    </Card>
  );
}
