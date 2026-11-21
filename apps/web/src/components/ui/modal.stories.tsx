"use client";

import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { useState } from "react";
import { Button } from "./button";
import { BottomSheet, Modal } from "./modal";

const meta = { title: "UI/Modal and BottomSheet" } satisfies Meta;
export default meta;
type Story = StoryObj;

function Demo({ sheet, startOpen }: { sheet?: boolean; startOpen?: boolean }) {
  const [open, setOpen] = useState(!!startOpen);
  const Comp = sheet ? BottomSheet : Modal;
  return (
    <>
      <Button variant="primary" onClick={() => setOpen(true)}>
        Open {sheet ? "sheet" : "dialog"}
      </Button>
      <Comp
        open={open}
        onClose={() => setOpen(false)}
        title="Delete your data?"
        description="This removes your profile, resumes and tracker. It can't be undone."
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="danger-solid" onClick={() => setOpen(false)}>
              Delete
            </Button>
          </>
        }
      >
        <p>Export a copy first from Settings if you want to keep it.</p>
      </Comp>
    </>
  );
}

export const Dialog: Story = { render: () => <Demo /> };
export const DialogOpen: Story = { render: () => <Demo startOpen /> };
export const Sheet: Story = { render: () => <Demo sheet /> };
