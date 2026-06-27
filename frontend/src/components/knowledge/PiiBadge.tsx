import { ShieldCheck, ShieldAlert, ShieldX } from "lucide-react";
import { cn } from "@/lib/utils";
import type { PIISummary } from "@/types/api";

/** T070 — PII 处置摘要展示.
 *
 * Renders a compact badge + popover detailing:
 *   - hit_count (total PII matches in parsed text)
 *   - fields[] (which PII categories were detected)
 *   - actions[] (replacements / redactions applied)
 *
 * Visual states:
 *   - has_pii = false  → 绿色 "已脱敏"
 *   - has_pii = true   → 黄色 "已处理 N 项" 或 红色 "需确认"（当动作被阻止时）
 */

const FIELD_LABELS: Record<string, string> = {
  phone: "手机号",
  email: "邮箱",
  id_card: "身份证",
  bank_card: "银行卡",
  address: "地址",
  name: "姓名",
  url: "链接",
  ip: "IP 地址",
};

function describeField(field: string): string {
  return FIELD_LABELS[field] ?? field;
}

/** True if at least one action was actually applied (a replacement was made).
 *  PII summaries that report `hit_count > 0` but no actions correspond to
 *  the "blocked" case — the sample was held for human review. */
function hasReplacements(summary: PIISummary | null | undefined): boolean {
  return (summary?.actions?.length ?? 0) > 0;
}

export interface PiiBadgeProps {
  summary: PIISummary | null | undefined;
  /** Pass true if any action taken was a "block" (sample held for review). */
  blocked?: boolean;
  className?: string;
  /** If provided, the badge becomes a button that opens a detail view. */
  onClick?: () => void;
}

const BASE_BADGE = "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs";
const GREEN = "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200";
const RED = "bg-red-50 text-red-700 ring-1 ring-red-200";
const AMBER = "bg-amber-50 text-amber-700 ring-1 ring-amber-200";

export function PiiBadge({ summary, blocked, className, onClick }: PiiBadgeProps) {
  const hasHits = (summary?.hit_count ?? 0) > 0;
  // Blocked = explicit prop OR no replacement was applied (only detected)
  const anyBlocked = blocked || (hasHits && !hasReplacements(summary));

  const colorClass = !hasHits ? GREEN : anyBlocked ? RED : AMBER;
  const tooltip = !hasHits
    ? "解析过程中未检测到 PII"
    : anyBlocked
      ? "检测到敏感信息且被阻断，请人工确认"
      : `已处理 ${summary?.hit_count} 项 PII：${(summary?.fields ?? []).map(describeField).join("、")}`;
  const label = !hasHits
    ? "已脱敏"
    : anyBlocked
      ? `需确认 · ${summary?.hit_count}`
      : `已处理 ${summary?.hit_count} 项`;
  const Icon = !hasHits ? ShieldCheck : anyBlocked ? ShieldX : ShieldAlert;

  const content = (
    <>
      <Icon className="h-3 w-3" aria-hidden />
      {label}
    </>
  );

  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        title={tooltip}
        className={cn(BASE_BADGE, colorClass, "cursor-pointer hover:opacity-80", className)}
      >
        {content}
      </button>
    );
  }

  return (
    <span
      title={tooltip}
      className={cn(BASE_BADGE, colorClass, className)}
    >
      {content}
    </span>
  );
}

/** Detailed panel — used in a side drawer or expand-on-click UI. */
export function PiiDetail({ summary }: { summary: PIISummary }) {
  return (
    <div className="space-y-3 text-sm">
      <div className="flex items-center justify-between">
        <span className="text-muted-foreground">命中总数</span>
        <span className="font-medium">{summary.hit_count}</span>
      </div>
      <div className="flex items-start justify-between gap-4">
        <span className="text-muted-foreground">涉及字段</span>
        <div className="flex flex-wrap justify-end gap-1">
          {(summary.fields ?? []).length === 0 ? (
            <span className="text-muted-foreground">—</span>
          ) : (
            summary.fields.map((f) => (
              <span
                key={f}
                className="rounded bg-secondary px-1.5 py-0.5 text-xs"
              >
                {describeField(f)}
              </span>
            ))
          )}
        </div>
      </div>
      {summary.actions && summary.actions.length > 0 && (
        <div>
          <div className="mb-1 text-muted-foreground">处置动作（前 10 条）</div>
          <ul className="space-y-1 rounded-md border bg-muted/30 p-2 text-xs">
            {summary.actions.slice(0, 10).map((a, i) => (
              <li key={i} className="flex items-center justify-between gap-2 font-mono">
                <span className="truncate">{describeField(a.field)}</span>
                <span className="shrink-0 text-muted-foreground">→ {a.replacement}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
