import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { StatusChip, MetricChip } from "./chip";
import { KanbanCard } from "./kanban-card";

const meta = { title: "UI/KanbanCard", component: KanbanCard } satisfies Meta<
  typeof KanbanCard
>;
export default meta;
type Story = StoryObj<typeof meta>;

const columns = ["Saved", "Applied", "Interview", "Offer"];
export const Default: Story = {
  args: {
    title: "Senior Frontend Engineer",
    subtitle: "Acme Labs",
    columnLabel: "Applied",
    columnIndex: 1,
    columnCount: 4,
    columnLabels: columns,
    meta: (
      <>
        <StatusChip>Applied 3d ago</StatusChip>
        <MetricChip>₹32 LPA</MetricChip>
      </>
    ),
  },
  render: (args) => (
    <ul className="m-0 max-w-sm list-none p-0">
      <KanbanCard {...args} />
    </ul>
  ),
};
