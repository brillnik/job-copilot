import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { Button } from "./button";
import { CheckChip, SourceChip } from "./chip";
import { InputField } from "./field";
import { KanbanCard } from "./kanban-card";
import { Modal } from "./modal";
import { ScoreBar, scoreLevel } from "./score-bar";
import { Segmented } from "./segmented";
import { Stepper } from "./stepper";
import { ToastProvider, useToast } from "./toast";
import { Toggle } from "./toggle";

describe("Button", () => {
  it("loading disables clicks, sets aria-busy and announces", async () => {
    const onClick = vi.fn();
    render(
      <Button loading onClick={onClick}>
        Save
      </Button>,
    );
    const b = screen.getByRole("button", { name: /save/i });
    expect(b).toBeDisabled();
    expect(b).toHaveAttribute("aria-busy", "true");
    await userEvent.click(b);
    expect(onClick).not.toHaveBeenCalled();
  });
  it("icon-only exposes its aria-label", () => {
    render(
      <Button iconOnly aria-label="Close">
        <svg />
      </Button>,
    );
    expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument();
  });
  it("defaults to type=button", () => {
    render(<Button>x</Button>);
    expect(screen.getByRole("button")).toHaveAttribute("type", "button");
  });
});

describe("InputField", () => {
  it("links label, hint and error to the input", () => {
    render(
      <InputField
        label="Email"
        hint="We never share it"
        error="Enter a valid email"
      />,
    );
    const input = screen.getByLabelText("Email");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription("Enter a valid email");
    expect(screen.getByRole("alert")).toHaveTextContent("Enter a valid email");
  });
  it("low confidence shows text, not just colour", () => {
    render(<InputField label="Title" lowConfidence />);
    expect(screen.getByText(/low confidence/i)).toBeInTheDocument();
  });
});

describe("ScoreBar", () => {
  it.each([
    [100, "ok"],
    [80, "ok"],
    [79, "warn"],
    [60, "warn"],
    [59, "bad"],
    [0, "bad"],
  ])("score %i is %s", (n, level) => expect(scoreLevel(n)).toBe(level));
  it("always shows the number and exposes a meter", () => {
    render(<ScoreBar score={72} />);
    expect(screen.getByText("72")).toBeInTheDocument();
    expect(screen.getByRole("meter", { name: "Match" })).toHaveAttribute(
      "aria-valuenow",
      "72",
    );
  });
});

describe("Chips", () => {
  it("SourceChip tooltip is described by the original text and reachable by keyboard", async () => {
    render(<SourceChip id="§exp.1" original="Original sentence" />);
    const chip = screen.getByRole("button", { name: "§exp.1" });
    await userEvent.tab();
    expect(chip).toHaveFocus();
    expect(chip).toHaveAccessibleDescription(/Original sentence/);
    expect(screen.getByRole("tooltip")).toHaveTextContent("Original sentence");
  });
  it("CheckChip carries its state as text", () => {
    render(<CheckChip state="missing">Rust</CheckChip>);
    expect(screen.getByText(/Missing:/)).toBeInTheDocument();
  });
});

describe("Segmented", () => {
  it("is a radiogroup that selects with the keyboard", async () => {
    function Demo() {
      const [v, setV] = useState("a");
      return (
        <Segmented
          label="Mode"
          value={v}
          onChange={setV}
          options={[
            { value: "a", label: "A" },
            { value: "b", label: "B" },
          ]}
        />
      );
    }
    render(<Demo />);
    const group = screen.getByRole("radiogroup", { name: "Mode" });
    expect(within(group).getByRole("radio", { name: "A" })).toBeChecked();
    await userEvent.tab();
    await userEvent.keyboard("{ArrowRight}");
    expect(within(group).getByRole("radio", { name: "B" })).toBeChecked();
  });
});

describe("Toggle", () => {
  it("is a switch that toggles", async () => {
    const fn = vi.fn();
    render(<Toggle label="Digest" checked={false} onCheckedChange={fn} />);
    const sw = screen.getByRole("switch", { name: "Digest" });
    expect(sw).toHaveAttribute("aria-checked", "false");
    await userEvent.click(sw);
    expect(fn).toHaveBeenCalledWith(true);
  });
});

describe("Stepper", () => {
  it("states are text, and the active step is marked", () => {
    render(
      <Stepper
        steps={[
          { label: "A", state: "done" },
          { label: "B", state: "running" },
          { label: "C", state: "queued" },
        ]}
      />,
    );
    expect(screen.getByText(/^Done/)).toBeInTheDocument();
    expect(screen.getByText(/^Running/)).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")[1]).toHaveAttribute(
      "aria-current",
      "step",
    );
  });
});

describe("KanbanCard", () => {
  it("moves between columns with the keyboard and announces", async () => {
    const onMove = vi.fn();
    render(
      <ul>
        <KanbanCard
          title="SWE"
          columnLabel="Saved"
          columnIndex={0}
          columnCount={3}
          columnLabels={["Saved", "Applied", "Offer"]}
          onMove={onMove}
        />
      </ul>,
    );
    const card = screen.getByRole("button", { name: /SWE/ });
    card.focus();
    await userEvent.keyboard(" ");
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByText(/Applied, position 2 of 3/)).toBeInTheDocument();
    await userEvent.keyboard(" ");
    expect(onMove).toHaveBeenCalledWith(1);
  });
  it("Escape cancels", async () => {
    const onMove = vi.fn();
    render(
      <ul>
        <KanbanCard
          title="SWE"
          columnLabel="Saved"
          columnIndex={0}
          columnCount={3}
          onMove={onMove}
        />
      </ul>,
    );
    screen.getByRole("button").focus();
    await userEvent.keyboard(" {ArrowRight}{Escape}");
    expect(onMove).not.toHaveBeenCalled();
  });
});

describe("Modal", () => {
  it("opens with a labelled title and closes via the close button", async () => {
    const onClose = vi.fn();
    render(
      <Modal open onClose={onClose} title="Confirm">
        body
      </Modal>,
    );
    expect(screen.getByRole("dialog", { name: "Confirm" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalled();
  });
});

describe("Toast", () => {
  it("pushes into a live region; errors use role=alert; dismissable", async () => {
    function Demo() {
      const { toast } = useToast();
      return (
        <button onClick={() => toast({ kind: "error", title: "Boom" })}>
          go
        </button>
      );
    }
    render(
      <ToastProvider>
        <Demo />
      </ToastProvider>,
    );
    await userEvent.click(screen.getByText("go"));
    expect(screen.getByRole("alert")).toHaveTextContent("Boom");
    await userEvent.click(
      screen.getByRole("button", { name: "Dismiss notification" }),
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
