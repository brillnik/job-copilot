import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { AnswerRow } from "@/features/screening/screening-answers";
import { PairCodeCard } from "@/features/integrations/pair-code-card";
import { RecommendationCard } from "@/features/recommendations/recommendation-card";
import { SuggestionCard } from "@/features/gmail/suggestion-card";
import { ApplicationRow } from "@/features/applications/application-list";

const noop = () => {};
const rec = {
  id: "r1",
  catalog_job_id: "c1",
  score: 86,
  reasons: ["Skills match: React, TypeScript", "Salary above your expectation"],
  digest_date: "2026-11-19",
  action: "none" as const,
  job_id: null,
  title: "Senior Frontend Engineer",
  company: "Acme",
  location: "Bengaluru",
  remote: true,
  apply_url: "https://example.com/apply",
  source_attribution: null,
};

const meta = { title: "Phase 4/Cards" } satisfies Meta;
export default meta;
type Story = StoryObj<typeof meta>;

export const Recommendation: Story = {
  render: () => <RecommendationCard rec={rec} onSave={noop} onDismiss={noop} />,
};
export const RecommendationWeak: Story = {
  render: () => (
    <RecommendationCard
      rec={{ ...rec, score: 41 }}
      onSave={noop}
      onDismiss={noop}
    />
  ),
};
export const RecommendationSaved: Story = {
  render: () => (
    <RecommendationCard
      rec={{ ...rec, action: "saved", job_id: "j1" }}
      onSave={noop}
      onDismiss={noop}
    />
  ),
};

export const PairCode: Story = {
  render: () => (
    <PairCodeCard
      code="ABCD-1234"
      expiresAt={new Date(Date.now() + 600_000).toISOString()}
      onRegenerate={noop}
    />
  ),
};
export const PairCodeExpired: Story = {
  render: () => (
    <PairCodeCard
      code="ABCD-1234"
      expiresAt="2020-01-01T00:00:00Z"
      onRegenerate={noop}
    />
  ),
};

const suggestion = {
  id: "s1",
  job_id: "j1",
  company: "Acme",
  title: "SWE",
  classification: "interview_invite",
  confidence: 0.91,
  suggested_column: "interview" as const,
  status: "pending" as const,
  received_at: "2026-11-19T00:00:00Z",
};
export const GmailSuggestion: Story = {
  render: () => (
    <SuggestionCard suggestion={suggestion} onConfirm={noop} onDismiss={noop} />
  ),
};
export const GmailSuggestionError: Story = {
  render: () => (
    <SuggestionCard
      suggestion={suggestion}
      onConfirm={noop}
      onDismiss={noop}
      error="That suggestion was already handled."
    />
  ),
};

export const ScreeningAnswer: Story = {
  render: () => (
    <AnswerRow
      answer={{
        id: "a1",
        question: "What is your notice period?",
        answer: "30 days",
        field_type: "text",
        source: "user",
        updated_at: "2026-11-01T00:00:00Z",
      }}
      onEdit={noop}
      onDelete={noop}
    />
  ),
};

const application = {
  id: "a1",
  job_id: "j1",
  run_id: "r1",
  company: "Beta",
  title: "Frontend Engineer",
  channel: "playwright" as const,
  mode: "autopilot" as const,
  ats: "greenhouse",
  site: "greenhouse",
  status: "skipped" as const,
  skip_reason: "captcha",
  direct_link: "https://beta.example/apply",
  submitted_at: null,
  answers_used: [],
  screenshots: [],
  pending_fields: [],
  attempts: 2,
  created_at: "2026-11-19T09:00:00Z",
  updated_at: "2026-11-19T10:00:00Z",
};
export const ApplicationSkipped: Story = {
  render: () => <ApplicationRow app={application} />,
};
export const ApplicationSubmitted: Story = {
  render: () => (
    <ApplicationRow
      app={{ ...application, status: "submitted", skip_reason: null }}
    />
  ),
};
