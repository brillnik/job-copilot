"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { InputField } from "@/components/ui/field";
import { Modal } from "@/components/ui/modal";
import { ApiError } from "@/lib/api/errors";
import { deleteAccount, isReauth, logoutEverywhere, reauthUrl } from "./api";

export const DELETED_PATH = "/account-deleted";

// Full-page navigations: /auth/* is served by the Auth0 SDK middleware.
function go(url: string) {
  window.location.assign(url);
}

export function AccountSection({
  autoOpenDelete = false,
}: {
  autoOpenDelete?: boolean;
}) {
  const [deleteOpen, setDeleteOpen] = useState(autoOpenDelete);
  const [everywhereOpen, setEverywhereOpen] = useState(false);
  const [typed, setTyped] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needsReauth, setNeedsReauth] = useState(false);

  async function confirmDelete() {
    setPending(true);
    setError(null);
    try {
      await deleteAccount();
      // 202: erasure started; every later request fails. Sign out, then show the confirmation page.
      go(`/auth/logout?returnTo=${encodeURIComponent(DELETED_PATH)}`);
    } catch (e) {
      setPending(false);
      if (isReauth(e)) setNeedsReauth(true);
      else if (e instanceof ApiError && e.status === 422)
        setError("Type DELETE exactly as shown to confirm.");
      else
        setError(
          e instanceof ApiError
            ? e.message
            : "Couldn't delete the account. Check your connection and try again.",
        );
    }
  }

  async function everywhere() {
    setPending(true);
    setError(null);
    try {
      await logoutEverywhere();
      go("/auth/logout");
    } catch (e) {
      setPending(false);
      setError(
        e instanceof ApiError
          ? e.message
          : "Couldn't sign out everywhere. Try again.",
      );
    }
  }

  return (
    <Card as="section" aria-labelledby="acct-h" className="flex flex-col gap-4">
      <div>
        <h2 id="acct-h" className="text-section font-semibold">
          Account
        </h2>
      </div>
      <div className="flex flex-col items-start gap-1.5">
        <p className="font-medium">Sign out everywhere</p>
        <p className="text-hint text-subtle">
          Ends every session and extension on all your devices, including this
          one.
        </p>
        <Button
          onClick={() => {
            setError(null);
            setEverywhereOpen(true);
          }}
        >
          Sign out everywhere
        </Button>
      </div>
      <div className="flex flex-col items-start gap-1.5 border-t border-border pt-4">
        <p className="font-medium">Delete account</p>
        <p className="text-hint text-subtle">
          Permanently erases your profile, resumes and applications within 24
          hours. This can&apos;t be undone.
        </p>
        <Button
          variant="danger"
          onClick={() => {
            setError(null);
            setNeedsReauth(false);
            setTyped("");
            setDeleteOpen(true);
          }}
        >
          Delete my account
        </Button>
      </div>

      <Modal
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        variant="sheet"
        title="Delete your account"
        description="All your data will be erased. Active runs are cancelled."
        footer={
          needsReauth ? (
            <>
              <Button variant="ghost" onClick={() => setDeleteOpen(false)}>
                Cancel
              </Button>
              <Button variant="primary" onClick={() => go(reauthUrl())}>
                Sign in again
              </Button>
            </>
          ) : (
            <>
              <Button variant="ghost" onClick={() => setDeleteOpen(false)}>
                Cancel
              </Button>
              <Button
                variant="danger-solid"
                loading={pending}
                disabled={typed !== "DELETE"}
                onClick={() => void confirmDelete()}
              >
                Delete account
              </Button>
            </>
          )
        }
      >
        {needsReauth ? (
          <p role="alert">
            For your security, sign in again to confirm it&apos;s you.
            You&apos;ll come back here to finish deleting your account.
          </p>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (typed === "DELETE") void confirmDelete();
            }}
            className="flex flex-col gap-3"
          >
            <InputField
              label="Type DELETE to confirm"
              value={typed}
              autoComplete="off"
              onChange={(e) => setTyped(e.target.value)}
            />
            <div role="alert">
              {error && <p className="font-medium text-bad">{error}</p>}
            </div>
          </form>
        )}
      </Modal>

      <Modal
        open={everywhereOpen}
        onClose={() => setEverywhereOpen(false)}
        variant="sheet"
        title="Sign out everywhere?"
        description="Every session and extension token stops working, including this one."
        footer={
          <>
            <Button variant="ghost" onClick={() => setEverywhereOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="primary"
              loading={pending}
              onClick={() => void everywhere()}
            >
              Sign out everywhere
            </Button>
          </>
        }
      >
        <div role="alert">
          {error && <p className="font-medium text-bad">{error}</p>}
        </div>
      </Modal>
    </Card>
  );
}
