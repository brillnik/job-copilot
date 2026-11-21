import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { Button } from "./button";
import { EmptyState } from "./empty-state";
import { ErrorState } from "./error-state";
import { InboxIcon } from "./icons";
import { Skeleton, SkeletonGroup } from "./skeleton";
import { Toast } from "./toast";

const meta = { title: "UI/Feedback states" } satisfies Meta;
export default meta;
type Story = StoryObj;

export const Toasts: Story = {
  render: () => (
    <div className="flex flex-col gap-3">
      <Toast kind="info" title="Draft saved" onDismiss={() => {}} />
      <Toast
        kind="success"
        title="Resume approved"
        description="PDF is ready to download."
        onDismiss={() => {}}
      />
      <Toast
        kind="error"
        title="Couldn't save"
        description="Check your connection."
        action={{ label: "Retry", onClick: () => {} }}
        onDismiss={() => {}}
      />
    </div>
  ),
};

export const Empty: Story = {
  render: () => (
    <EmptyState
      icon={<InboxIcon className="size-6" />}
      title="Nothing in your inbox yet"
      description="Paste a job link or use the browser extension to add your first job."
      action={<Button variant="primary">Add a job</Button>}
    />
  ),
};

export const Loading: Story = {
  render: () => (
    <SkeletonGroup
      label="Loading jobs"
      className="flex max-w-md flex-col gap-3"
    >
      <Skeleton className="h-6 w-2/3" />
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-5/6" />
      <Skeleton className="h-24 w-full" />
    </SkeletonGroup>
  ),
};

export const ErrorWithRetry: Story = {
  render: () => (
    <ErrorState message="We couldn't load your jobs." onRetry={() => {}} />
  ),
};
export const ErrorRetrying: Story = {
  render: () => (
    <ErrorState
      message="We couldn't load your jobs."
      onRetry={() => {}}
      retrying
    />
  ),
};
