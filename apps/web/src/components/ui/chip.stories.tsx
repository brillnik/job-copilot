import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import {
  CheckChip,
  Chip,
  ComingSoonChip,
  MetricChip,
  RedFlagChip,
  SkillChip,
  SourceChip,
  StatusChip,
} from "./chip";

const meta = {
  title: "UI/Chip",
  component: Chip,
  args: { children: "Setup" },
} satisfies Meta<typeof Chip>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Neutral: Story = {};
export const Current: Story = {
  args: { current: true, children: "1 · Sign in" },
};
export const Skill: StoryObj = {
  render: () => <SkillChip>TypeScript</SkillChip>,
};
export const Metric: StoryObj = {
  render: () => <MetricChip>₹32 LPA</MetricChip>,
};
export const Source: StoryObj = {
  render: () => (
    <div className="pt-16">
      <SourceChip
        id="§exp.2.b3"
        original="Led migration of the billing service to Postgres, cutting p95 latency by 38%."
      />
    </div>
  ),
};
export const Status: StoryObj = {
  render: () => (
    <div className="flex flex-wrap gap-2">
      <StatusChip>Saved</StatusChip>
      <StatusChip tone="accent">In review</StatusChip>
      <StatusChip tone="ok">Approved</StatusChip>
      <StatusChip tone="warn">Needs attention</StatusChip>
      <StatusChip tone="bad">Rejected</StatusChip>
    </div>
  ),
};
export const Check: StoryObj = {
  render: () => (
    <div className="flex flex-wrap gap-2">
      <CheckChip state="have">React</CheckChip>
      <CheckChip state="ask">Kubernetes</CheckChip>
      <CheckChip state="missing">Rust</CheckChip>
    </div>
  ),
};
export const RedFlag: StoryObj = {
  render: () => <RedFlagChip>Unpaid trial week</RedFlagChip>,
};
export const ComingSoon: StoryObj = { render: () => <ComingSoonChip /> };
