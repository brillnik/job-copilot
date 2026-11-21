"use client";

import { Segmented } from "@/components/ui/segmented";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api/errors";
import { useSaveTheme } from "@/hooks/use-settings";
import { useToast } from "@/components/ui/toast";
import { useTheme } from "@/providers/theme-provider";
import type { Theme } from "@/lib/theme";

const OPTIONS = [
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
  { value: "system", label: "System" },
] as const;

export function AppearanceSettings() {
  const { theme, setTheme, resolved } = useTheme();
  const { toast } = useToast();
  // ThemeSync persists in the background; this surfaces nothing on failure by
  // design (the local choice still applies), but the explicit retry reports errors.
  const save = useSaveTheme();

  return (
    <Card
      as="section"
      aria-labelledby="appearance-h"
      className="flex flex-col gap-4"
    >
      <div>
        <h2 id="appearance-h" className="text-section font-semibold">
          Appearance
        </h2>
        <p className="text-muted">
          Choose a theme. “System” follows your device and is currently{" "}
          {resolved}.
        </p>
      </div>
      <Segmented<Theme>
        label="Theme"
        options={OPTIONS}
        value={theme}
        onChange={setTheme}
      />
      <div>
        <Button
          variant="secondary"
          size="sm"
          loading={save.isPending}
          onClick={() =>
            save.mutate(theme, {
              onSuccess: () =>
                toast({
                  kind: "success",
                  title: "Theme saved to your account",
                }),
              onError: (e) =>
                toast({
                  kind: "error",
                  title: "Couldn't save theme",
                  description: errorMessage(e),
                }),
            })
          }
        >
          Save to my account
        </Button>
        <p className="mt-1.5 text-hint text-subtle">
          Your choice is already remembered on this device and synced
          automatically once you&apos;re set up.
        </p>
      </div>
      <p className="text-hint text-subtle">
        <a
          href="/auth/logout"
          className="font-medium text-accent-text underline underline-offset-2"
        >
          Sign out
        </a>
      </p>
    </Card>
  );
}
