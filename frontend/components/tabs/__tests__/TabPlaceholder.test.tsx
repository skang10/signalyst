import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { TabPlaceholder } from "../TabPlaceholder";

describe("TabPlaceholder", () => {
  it("renders the icon, title, and reason", () => {
    render(
      <TabPlaceholder
        icon="≡"
        title="Feature importance not available"
        reason="Not computed in this run."
      />
    );
    expect(screen.getByText("≡")).toBeTruthy();
    expect(screen.getByText("Feature importance not available")).toBeTruthy();
    expect(screen.getByText("Not computed in this run.")).toBeTruthy();
  });
});
