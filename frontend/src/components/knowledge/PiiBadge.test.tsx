import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PiiBadge, PiiDetail } from "./PiiBadge";
import type { PIISummary } from "@/types/api";

describe("PiiBadge", () => {
  it('renders "已脱敏" (green) when no hits', () => {
    const { container } = render(<PiiBadge summary={null} />);
    expect(screen.getByText("已脱敏")).toBeInTheDocument();
    expect(container.firstChild).toHaveClass("bg-emerald-50");
  });

  it("renders 0-hit summary as 已脱敏", () => {
    const summary: PIISummary = { hit_count: 0, fields: [], actions: [] };
    render(<PiiBadge summary={summary} />);
    expect(screen.getByText("已脱敏")).toBeInTheDocument();
  });

  it("renders '已处理 N 项' (amber) when replacements exist", () => {
    const summary: PIISummary = {
      hit_count: 2,
      fields: ["phone", "email"],
      actions: [
        { field: "phone", start: 0, end: 11, score: 0.99, replacement: "***" },
        { field: "email", start: 12, end: 30, score: 0.95, replacement: "***" },
      ],
    };
    const { container } = render(<PiiBadge summary={summary} />);
    expect(screen.getByText("已处理 2 项")).toBeInTheDocument();
    expect(container.firstChild).toHaveClass("bg-amber-50");
  });

  it("renders '需确认' (red) when hits exist but no replacements were applied", () => {
    const summary: PIISummary = {
      hit_count: 1,
      fields: ["id_card"],
      actions: [],
    };
    const { container } = render(<PiiBadge summary={summary} />);
    expect(screen.getByText("需确认 · 1")).toBeInTheDocument();
    expect(container.firstChild).toHaveClass("bg-red-50");
  });

  it("explicit blocked prop forces red state", () => {
    const summary: PIISummary = {
      hit_count: 1,
      fields: ["phone"],
      actions: [{ field: "phone", start: 0, end: 11, score: 0.99, replacement: "***" }],
    };
    const { container } = render(<PiiBadge summary={summary} blocked />);
    expect(screen.getByText("需确认 · 1")).toBeInTheDocument();
    expect(container.firstChild).toHaveClass("bg-red-50");
  });

  it("becomes a button when onClick is provided and fires the handler", async () => {
    const onClick = vi.fn();
    const summary: PIISummary = {
      hit_count: 1,
      fields: ["phone"],
      actions: [{ field: "phone", start: 0, end: 11, score: 0.99, replacement: "***" }],
    };
    render(<PiiBadge summary={summary} onClick={onClick} />);
    await userEvent.click(screen.getByRole("button"));
    expect(onClick).toHaveBeenCalledTimes(1);
  });
});

describe("PiiDetail", () => {
  it("shows hit count and a chip per field", () => {
    const summary: PIISummary = {
      hit_count: 2,
      fields: ["phone", "email"],
      actions: [],
    };
    render(<PiiDetail summary={summary} />);
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("手机号")).toBeInTheDocument();
    expect(screen.getByText("邮箱")).toBeInTheDocument();
  });

  it("renders the first 10 actions with field + replacement", () => {
    const summary: PIISummary = {
      hit_count: 12,
      fields: ["phone"],
      actions: Array.from({ length: 12 }, (_, i) => ({
        field: "phone",
        start: i,
        end: i + 1,
        score: 0.9,
        replacement: `***${i}`,
      })),
    };
    render(<PiiDetail summary={summary} />);
    // 10 rows shown, "前 10 条" caption present
    expect(screen.getByText(/前 10 条/)).toBeInTheDocument();
    // The 11th replacement must NOT appear
    expect(screen.queryByText("***10")).not.toBeInTheDocument();
  });
});
