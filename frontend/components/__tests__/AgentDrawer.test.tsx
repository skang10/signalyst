import { render, screen } from "@testing-library/react";
import { describe, it, expect, beforeEach } from "vitest";
import { AgentDrawer } from "../AgentDrawer";
import { useRunStore } from "@/lib/store";
import type { StreamMessage } from "@/lib/websocket";

beforeEach(() => {
  useRunStore.setState({ messages: [], status: "idle", result: null, error: null, runId: null });
});

describe("AgentDrawer", () => {
  it("is hidden when isOpen is false", () => {
    const { container } = render(<AgentDrawer isOpen={false} />);
    expect(container.firstChild).toHaveClass("w-0");
  });

  it("renders as a right-side panel when isOpen is true", () => {
    const { container } = render(<AgentDrawer isOpen={true} />);
    expect(container.firstChild).toHaveClass("w-[390px]");
    expect(screen.getByText("Agent progress")).toBeTruthy();
  });

  it("renders 9 phase dots (one per phase)", () => {
    useRunStore.setState({
      status: "running",
      messages: [{ type: "phase", phase: "discovering_data_sources" }],
    });
    const { container } = render(<AgentDrawer isOpen={true} />);
    const phaseDots = container.querySelectorAll("[data-phase-dot]");
    expect(phaseDots.length).toBe(9);
  });

  it("shows latest thought from running phase", () => {
    const messages: StreamMessage[] = [
      { type: "phase", phase: "predicting_regime" },
      { type: "thought", content: "Classifying regime with TabPFN…" },
    ];
    useRunStore.setState({ messages, status: "running" });
    render(<AgentDrawer isOpen={true} />);
    expect(screen.getByText("Classifying regime with TabPFN…")).toBeTruthy();
  });

  it("shows no thought text when messages is empty", () => {
    useRunStore.setState({ messages: [], status: "running" });
    const { container } = render(<AgentDrawer isOpen={true} />);
    expect(container).not.toHaveTextContent("Classifying regime with TabPFN…");
  });
});
