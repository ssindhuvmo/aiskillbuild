// Career Profile options. Must match backend/core/agents/intake/validation.py.
export const LEVELS = ["None", "Beginner", "Intermediate", "Experienced"];
// Skill-gap targets may go one step beyond the ratings (gap_analysis/schemas.py).
export const TARGET_LEVELS = [...LEVELS, "Expert"];

export const CAPABILITY_AREAS = {
  python: "Python",
  data_sql: "Data and SQL",
  machine_learning: "Machine Learning",
  ai_llms: "AI / LLMs",
  cloud: "Cloud",
};

export const PREFERENCES = {
  free_courses: "Free courses",
  paid_courses: "Paid courses",
  video: "YouTube / video",
  articles: "Articles",
  books: "Books",
  projects: "Hands-on projects",
  certifications: "Certifications",
};
export const DEFAULT_PREFERENCES = ["free_courses", "video", "articles", "projects"];

export const BUDGETS = { free_only: "Free only", monthly: "Monthly budget" };
export const CONSTRAINT_FLAGS = {
  weekends_only: "Weekends only",
  keep_current_job: "Must stay in current job",
  remote_only: "Remote only",
};

export const ratedCount = (capabilities) => Object.keys(CAPABILITY_AREAS).filter((a) => capabilities?.[a]).length;

export function describePreferences(prefs) {
  if (prefs == null) return null;
  return prefs.map((p) => PREFERENCES[p] ?? p).join(", ");
}

// null = not asked yet, {} = none.
export function describeConstraints(c) {
  if (c == null) return null;
  const parts = [];
  if (c.budget === "free_only") parts.push("Free only");
  if (c.budget === "monthly") parts.push(`Up to ${c.monthly_budget} a month`);
  for (const [k, label] of Object.entries(CONSTRAINT_FLAGS)) if (c[k]) parts.push(label);
  if (c.other) parts.push(c.other);
  return parts.length ? parts.join(", ") : "None";
}
