import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { Dropzone } from "./dropzone";

const meta = {
  title: "UI/Dropzone",
  component: Dropzone,
  args: {
    label: "Upload your resume",
    hint: "PDF or DOCX, up to 5 MB.",
    accept: ".pdf,.docx",
    onFile: () => {},
  },
} satisfies Meta<typeof Dropzone>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Empty: Story = {};
export const Selected: Story = {
  args: { selected: { name: "nikhil-resume.pdf", detail: "212 KB" } },
};
export const WithError: Story = {
  args: { error: "This file is 7.2 MB. The limit is 5 MB." },
};
export const Disabled: Story = { args: { disabled: true } };
