import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { useState } from "react";
import { CheckboxGroup } from "./checkbox-group";
import { TagInput } from "./tag-input";

const meta = { title: "UI/Multi-value inputs", component: TagInput } satisfies Meta<typeof TagInput>;
export default meta;
type Story = StoryObj<typeof meta>;

function TagsDemo(args: React.ComponentProps<typeof TagInput>) {
  const [values, setValues] = useState(["Frontend Engineer", "Staff Engineer"]);
  return <TagInput {...args} values={values} onChange={setValues} max={10} placeholder="e.g. Frontend Engineer" />;
}

const OPTIONS = ["Remote", "Bengaluru", "Hyderabad", "Pune", "Mumbai", "Delhi NCR"] as const;
function CitiesDemo() {
  const [values, setValues] = useState<string[]>(["Bengaluru"]);
  return <CheckboxGroup legend="Cities" options={OPTIONS} values={values} onChange={setValues} hint="Pick every city you'd work in." />;
}

export const Tags: Story = {
  args: { label: "Target roles", values: [], onChange: () => {}, max: 10 },
  render: (args) => <TagsDemo {...args} />,
};

export const TagsWithError: Story = {
  args: { label: "Target roles", values: [], onChange: () => {} },
  render: (args) => <TagInput {...args} error="Add at least one target role" max={10} />,
};

export const Cities: Story = {
  args: { label: "x", values: [], onChange: () => {} },
  render: () => <CitiesDemo />,
};
