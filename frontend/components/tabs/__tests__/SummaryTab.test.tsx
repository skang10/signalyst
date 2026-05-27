import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { SummaryTab } from "../SummaryTab";

describe("SummaryTab", () => {
  it("renders the summary text", () => {
    render(<SummaryTab summary="Range-bound regime with high confidence. **Strong** signals." />);
    expect(screen.getByText(/range-bound regime/i)).toBeTruthy();
  });

  it("renders bold text from **markdown**", () => {
    render(<SummaryTab summary="This is **important**." />);
    const strong = document.querySelector("strong");
    expect(strong?.textContent).toBe("important");
  });

  it("renders placeholder when summary is empty", () => {
    render(<SummaryTab summary="" />);
    expect(screen.getByText(/no summary available/i)).toBeTruthy();
  });
});
