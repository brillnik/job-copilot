import { cn } from "@/lib/cn";

/** radius 12 on desktop, 18 on mobile. */
export function Card({
  className,
  as,
  ...props
}: React.ComponentProps<"div"> & {
  as?: "div" | "section" | "article" | "li";
}) {
  const Tag = (as ?? "div") as "div";
  return (
    <Tag
      className={cn(
        "rounded-card-mobile border border-border bg-surface p-4 md:rounded-card md:p-5",
        className,
      )}
      {...props}
    />
  );
}
