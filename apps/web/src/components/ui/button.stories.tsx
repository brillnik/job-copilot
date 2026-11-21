import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { Button, type ButtonSize, type ButtonVariant } from "./button";
import { XIcon } from "./icons";

const meta = {
  title: "UI/Button",
  component: Button,
  args: { children: "Tailor resume" },
} satisfies Meta<typeof Button>;
export default meta;
type Story = StoryObj<typeof meta>;

const variants: ButtonVariant[] = [
  "primary",
  "secondary",
  "ghost",
  "danger",
  "danger-solid",
];
const sizes: ButtonSize[] = ["sm", "md", "lg"];

export const Primary: Story = { args: { variant: "primary" } };
export const Secondary: Story = { args: { variant: "secondary" } };
export const Ghost: Story = { args: { variant: "ghost" } };
export const Danger: Story = {
  args: { variant: "danger", children: "Reject draft" },
};
export const DangerSolid: Story = {
  args: { variant: "danger-solid", children: "Delete my data" },
};
export const Loading: Story = {
  args: { variant: "primary", loading: true, children: "Saving" },
};
export const Disabled: Story = { args: { variant: "primary", disabled: true } };
export const IconOnly: Story = {
  args: {
    iconOnly: true,
    "aria-label": "Close",
    variant: "secondary",
    children: <XIcon />,
  },
};

export const AllVariantsAndSizes: Story = {
  render: () => (
    <div className="flex flex-col gap-4">
      {variants.map((v) => (
        <div key={v} className="flex flex-wrap items-center gap-3">
          {sizes.map((s) => (
            <Button key={s} variant={v} size={s}>
              {v} {s}
            </Button>
          ))}
          <Button variant={v} loading>
            Loading
          </Button>
          <Button variant={v} disabled>
            Disabled
          </Button>
          <Button variant={v} iconOnly aria-label={`${v} icon button`}>
            <XIcon />
          </Button>
        </div>
      ))}
    </div>
  ),
};
