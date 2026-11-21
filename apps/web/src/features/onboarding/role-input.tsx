"use client";

import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { Input } from "@/components/ui/input";
import { XIcon } from "@/components/ui/icons";

/** Add-by-typing list of roles (1-10, each up to 80 characters). */
export function RoleInput({
  roles,
  onChange,
  error,
}: {
  roles: string[];
  onChange: (roles: string[]) => void;
  error?: string;
}) {
  const id = useId();
  const [text, setText] = useState("");
  const [local, setLocal] = useState<string>();

  function add() {
    const r = text.trim();
    if (!r) return;
    if (r.length > 80) return setLocal("Keep each role under 80 characters");
    if (roles.some((x) => x.toLowerCase() === r.toLowerCase()))
      return setLocal("You already added that role");
    if (roles.length >= 10) return setLocal("At most 10 roles");
    setLocal(undefined);
    onChange([...roles, r]);
    setText("");
  }
  const shown = local ?? error;

  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-[13px] font-medium">
        Roles you&apos;re targeting
      </label>
      <div className="flex gap-2">
        <Input
          id={id}
          value={text}
          placeholder="e.g. Frontend Engineer"
          aria-invalid={shown ? true : undefined}
          aria-describedby={shown ? `${id}-err` : undefined}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              add();
            }
          }}
        />
        <Button onClick={add}>Add role</Button>
      </div>
      {shown && (
        <p id={`${id}-err`} role="alert" className="mt-1.5 text-hint font-medium text-bad">
          {shown}
        </p>
      )}
      {roles.length > 0 && (
        <ul aria-label="Selected roles" className="mt-2 flex flex-wrap gap-2">
          {roles.map((r) => (
            <li key={r}>
              <Chip className="gap-1.5 py-0.5 pr-1 text-[13px]">
                {r}
                <button
                  type="button"
                  aria-label={`Remove ${r}`}
                  onClick={() => onChange(roles.filter((x) => x !== r))}
                  className="grid size-6 place-items-center rounded-full hover:bg-border"
                >
                  <XIcon className="size-3.5" />
                </button>
              </Chip>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
