import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { useState } from "react";
import { BulletCard } from "./bullet-card";
import { CoveragePanel } from "./coverage-panel";
import { FactCheckPanel } from "./fact-check-panel";
import { runFixture } from "./fixtures";
import { PageFit } from "./page-fit";

const meta = { title: "Review/Panels", component: FactCheckPanel } satisfies Meta<typeof FactCheckPanel>;
export default meta;
type Story = StoryObj<typeof meta>;

function PageFitDemo() {
  const [length, setLength] = useState<1 | 2 | 3>(2);
  return <PageFit count={2} lastPageFill={0.4} maxPages={2} length={length} onLengthChange={setLength} onRegenerate={() => {}} />;
}

export const FactCheckClean: Story = { args: { violations: [], flagged: false } };
export const FactCheckFlagged: Story = {
  args: {
    flagged: true,
    violations: [
      { code: "unsupported_skill", field: "skills_order", source_id: null, term: "GraphQL", message: "GraphQL is not in your profile", blocked: false },
    ],
    refused: [
      { code: "invented_number", field: "summary", source_id: null, term: "10", message: "10 is not in your profile", blocked: true },
    ],
  },
};

export const Coverage: Story = {
  args: { violations: [], flagged: false },
  render: () => <CoveragePanel covered={["React", "TypeScript"]} missing={["GraphQL"]} pct={0.67} />,
};

export const PageFitOk: Story = {
  args: { violations: [], flagged: false },
  render: () => <PageFitDemo />,
};

export const PageFitTooLong: Story = {
  args: { violations: [], flagged: false },
  render: () => <PageFit count={3} lastPageFill={0.15} maxPages={2} length={2} onLengthChange={() => {}} onRegenerate={() => {}} />,
};

export const BulletRevertedAndRefused: Story = {
  args: { violations: [], flagged: false },
  render: () => {
    const { bullets } = runFixture();
    return (
      <ul className="m-0 flex list-none flex-col gap-3 p-0">
        <BulletCard bullet={bullets[0]} editable />
        <BulletCard
          bullet={bullets[1]}
          editable
          value="Cut build times by 90%"
          refused={[{ code: "invented_number", field: "bullet", source_id: "exp.0.b2", term: "90", message: "90 is not in your profile", blocked: true }]}
        />
      </ul>
    );
  },
};
