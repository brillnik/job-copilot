"use client";

import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { useState } from "react";
import { Segmented } from "./segmented";
import { Toggle } from "./toggle";

const meta = { title: "UI/Segmented and Toggle" } satisfies Meta;
export default meta;
type Story = StoryObj;

function SegDemo({ initial }: { initial: "light" | "dark" | "system" }) {
  const [v, setV] = useState(initial);
  return (
    <Segmented
      label="Theme"
      value={v}
      onChange={setV}
      options={[
        { value: "light", label: "Light" },
        { value: "dark", label: "Dark" },
        { value: "system", label: "System" },
      ]}
    />
  );
}

export const SegmentedControl: Story = {
  render: () => <SegDemo initial="system" />,
};

function ToggleDemo({
  initial,
  disabled,
}: {
  initial: boolean;
  disabled?: boolean;
}) {
  const [on, setOn] = useState(initial);
  return (
    <Toggle
      label={
        disabled
          ? "Autopilot (disabled)"
          : initial
            ? "Daily digest"
            : "Weekly summary"
      }
      hint="Email me a summary of activity"
      checked={on}
      onCheckedChange={setOn}
      disabled={disabled}
    />
  );
}

export const ToggleStates: Story = {
  render: () => (
    <div className="flex max-w-md flex-col gap-2">
      <ToggleDemo initial={true} />
      <ToggleDemo initial={false} />
      <ToggleDemo initial={true} disabled />
    </div>
  ),
};
