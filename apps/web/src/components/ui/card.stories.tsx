import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { Card } from "./card";
import { ScoreBar } from "./score-bar";
import { StatusChip } from "./chip";

const meta = { title: "UI/Card", component: Card } satisfies Meta<typeof Card>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <Card className="max-w-md">
      <div className="mb-2 flex items-start justify-between gap-3">
        <div>
          <h3 className="text-section font-semibold">
            Senior Frontend Engineer
          </h3>
          <p className="text-muted">Acme Labs · Bengaluru</p>
        </div>
        <StatusChip tone="accent">In review</StatusChip>
      </div>
      <ScoreBar score={84} />
    </Card>
  ),
};
