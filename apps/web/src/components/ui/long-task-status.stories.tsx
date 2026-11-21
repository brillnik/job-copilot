import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { Button } from "./button";
import { LongTaskStatus } from "./long-task-status";

const meta = {
  title: "UI/LongTaskStatus",
  component: LongTaskStatus,
  args: { label: "Reading your resume…" },
} satisfies Meta<typeof LongTaskStatus>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const WithAction: Story = {
  args: {
    slowAfterSeconds: 0,
    slowMessage: "Still working. Local models can take a few minutes.",
    action: <Button variant="ghost">Stop waiting</Button>,
  },
};
