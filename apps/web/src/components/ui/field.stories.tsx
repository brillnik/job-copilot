import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { InputField, SelectField, TextareaField } from "./field";

const meta = {
  title: "UI/Fields",
  component: InputField,
  args: { label: "Current CTC (LPA)" },
} satisfies Meta<typeof InputField>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = { args: { placeholder: "e.g. 18" } };
export const WithHint: Story = {
  args: { hint: "Annual, in lakhs. Only you can see this." },
};
export const WithError: Story = {
  args: { error: "Enter a number between 0 and 500", defaultValue: "abc" },
};
export const LowConfidence: Story = {
  args: { lowConfidence: true, defaultValue: "Sr. Eng (inferred)" },
};
export const MissingValueFlag: Story = {
  args: { lowConfidence: true, flagText: "Missing: no end date was found." },
};
export const Disabled: Story = {
  args: { disabled: true, defaultValue: "locked" },
};

export const TextareaStates: StoryObj = {
  render: () => (
    <div className="flex max-w-md flex-col gap-5">
      <TextareaField label="Summary" hint="Two or three sentences." />
      <TextareaField label="Summary" error="Summary is required" />
      <TextareaField
        label="Summary"
        lowConfidence
        defaultValue="Experienced engineer (inferred from resume)."
      />
    </div>
  ),
};

export const SelectStates: StoryObj = {
  render: () => (
    <div className="flex max-w-md flex-col gap-5">
      <SelectField label="Resume length" hint="Auto picks per job.">
        <option>Auto</option>
        <option>1 page</option>
        <option>2 pages</option>
      </SelectField>
      <SelectField label="Template" error="Pick a template">
        <option value="">Choose…</option>
        <option>Classic</option>
      </SelectField>
      <SelectField label="Notice period" lowConfidence>
        <option>30 days</option>
        <option>60 days</option>
      </SelectField>
    </div>
  ),
};
