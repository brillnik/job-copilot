import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { ScoreBar } from "./score-bar";

const meta = {
  title: "UI/ScoreBar",
  component: ScoreBar,
  args: { score: 86 },
} satisfies Meta<typeof ScoreBar>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Ok: Story = { args: { score: 86 } };
export const OkBoundary: Story = { args: { score: 80 } };
export const Warn: Story = { args: { score: 72 } };
export const WarnBoundary: Story = { args: { score: 60 } };
export const Bad: Story = { args: { score: 41 } };
export const Zero: Story = { args: { score: 0 } };
export const InCard: Story = {
  render: () => (
    <div className="w-72">
      <ScoreBar score={91} label="Match score" />
    </div>
  ),
};
