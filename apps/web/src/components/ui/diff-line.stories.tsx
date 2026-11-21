import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { DiffLine } from "./diff-line";

const meta = { title: "UI/DiffLine", component: DiffLine } satisfies Meta<
  typeof DiffLine
>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Master: Story = {
  args: {
    side: "master",
    segments: [
      { text: "Built " },
      { text: "internal dashboards", kind: "del" },
      { text: " used by the support team" },
    ],
  },
};
export const Tailored: Story = {
  args: {
    side: "tailored",
    segments: [
      { text: "Built " },
      { text: "React analytics dashboards", kind: "ins" },
      { text: " used by the support team" },
    ],
  },
};
export const Unchanged: Story = {
  args: {
    side: "tailored",
    segments: [{ text: "Mentored 3 junior engineers." }],
  },
};
export const Pair: Story = {
  args: { side: "master", segments: [] },
  render: () => (
    <div className="grid gap-2 md:grid-cols-2">
      <DiffLine
        side="master"
        segments={[
          { text: "Cut p95 latency " },
          { text: "by 30%", kind: "del" },
        ]}
      />
      <DiffLine
        side="tailored"
        segments={[
          { text: "Cut p95 latency " },
          { text: "by 38%", kind: "ins" },
        ]}
      />
    </div>
  ),
};
