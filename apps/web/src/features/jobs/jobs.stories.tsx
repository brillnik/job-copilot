"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { MustChips } from "./musts";
import { JobRow } from "./job-row";
import { PastePanel } from "./paste-panel";
import { QuestionCard } from "./question-card";
import { RedFlagDialog } from "./red-flag-dialog";
import type { JobSummary } from "./types";

const base: JobSummary = {
  id: "j1",
  company: "Acme",
  title: "Frontend Engineer",
  location: "Bengaluru",
  ctc_lpa_min: 30,
  ctc_lpa_max: 40,
  score: 82,
  musts_summary: "4 of 6",
  status: "new",
  red_flags: [],
  created_at: "2026-01-05T10:00:00Z",
};

const meta = { title: "Jobs/Inbox" } satisfies Meta;
export default meta;
type Story = StoryObj;

export const Rows: Story = {
  render: () => (
    <ul className="flex flex-col gap-3">
      <JobRow job={base} selected={false} onSelect={() => {}} />
      <JobRow
        job={{ ...base, id: "j2", score: 55, red_flags: ["Unpaid trial"] }}
        selected
        onSelect={() => {}}
      />
      <JobRow
        job={{
          ...base,
          id: "j3",
          status: "processing",
          title: null,
          company: null,
          score: null,
        }}
      />
      <JobRow job={{ ...base, id: "j4", status: "approved" }} />
    </ul>
  ),
};

export const NeedsPaste: Story = {
  render: () => (
    <ul>
      <JobRow job={{ ...base, status: "needs_paste", score: null }}>
        <PastePanel
          idPrefix="s1"
          reason="The page needs a login"
          onSubmit={async () => {}}
        />
      </JobRow>
    </ul>
  ),
};

export const Failed: Story = {
  render: () => (
    <ul>
      <JobRow job={{ ...base, status: "failed", score: null }}>
        <PastePanel idPrefix="s2" failed onSubmit={async () => {}} />
      </JobRow>
    </ul>
  ),
};

export const MustHaves: Story = {
  render: () => (
    <MustChips
      musts={[
        {
          skill: "React",
          status: "have",
          evidence_bullet_id: "abcdef0123456789",
        },
        { skill: "GraphQL", status: "ask" },
        { skill: "Go", status: "missing" },
        { skill: "Rust", status: "unknown" },
      ]}
      bulletTexts={new Map([["abcdef0123456789", "Shipped the design system"]])}
    />
  ),
};

export const Questions: Story = {
  render: () => (
    <QuestionCard
      questions={[
        { skill: "GraphQL", prompt: "Have you used GraphQL in production?" },
        { skill: "Go", prompt: null },
      ]}
      onSubmit={async () => {}}
    />
  ),
};

function RedFlagsDemo() {
  const [open, setOpen] = useState(true);
  return (
    <>
      <Button variant="primary" onClick={() => setOpen(true)}>
        Tailor resume
      </Button>
      <RedFlagDialog
        open={open}
        flags={["Unpaid trial period", "Pay a fee to apply"]}
        onCancel={() => setOpen(false)}
        onConfirm={() => setOpen(false)}
      />
    </>
  );
}

export const RedFlags: Story = { render: () => <RedFlagsDemo /> };
