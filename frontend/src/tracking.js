// Labels for the roadmap tracking the backend works out (core/agents/scheduler/tracking.py).

export const STATUS = {
  done: "Done",
  overdue: "Overdue",
  this_week: "This week",
  not_started: "Not started",
  in_progress: "In progress",
  empty: "Nothing planned",
};

// SkillBadge kind for a status or priority pill.
export const STATUS_KIND = { done: "done", overdue: "overdue", in_progress: "skill", this_week: "skill" };
export const PRIORITY_KIND = { high: "gap", medium: "plain", low: "plain" };

// "2026-11-08" -> "8 Nov" (or "8 Nov 2026" with year). Parsed as a local date, so it never shifts a day.
export function formatDay(iso, year = false) {
  if (!iso) return "";
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { day: "numeric", month: "short", ...(year && { year: "numeric" }) });
}
