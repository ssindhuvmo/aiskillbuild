import FilterChip from "./FilterChip.jsx";

// Mirrors backend/core/agents/course_search/schemas.py (TypeGroup, TYPE_OF) and knowledge/schemas.py (Level).
export const LEVEL_OPTIONS = [
  ["beginner", "Beginner"],
  ["intermediate", "Intermediate"],
  ["advanced", "Advanced"],
];
export const TYPE_OPTIONS = [
  ["course", "Course"],
  ["video", "Video"],
  ["article", "Article"],
  ["repository", "GitHub Repository"],
  ["book", "Book"],
  ["project", "Project"],
];
const COST_OPTIONS = [
  ["free", "Free"],
  ["paid", "Paid"],
];

// [] (no filter) shows every chip pressed. Turning off the last pressed chip clears the filter again.
function toggled(selected, all, key) {
  const current = selected.length ? selected : all;
  const next = current.includes(key) ? current.filter((k) => k !== key) : [...current, key];
  return next.length === 0 || next.length === all.length ? [] : all.filter((k) => next.includes(k));
}

// The filter chips. Each click changes the list itself (onChange posts to /api/resources/filter), so what
// is shown is what gets approved.
export default function ResourceFilters({ preferences, freeOnly, disabled, onChange }) {
  const { cost, levels, types } = preferences;
  const costs = freeOnly ? ["free"] : cost === "any" ? [] : [cost];
  const levelKeys = LEVEL_OPTIONS.map(([k]) => k);
  const typeKeys = TYPE_OPTIONS.map(([k]) => k);
  const change = (patch) => onChange({ cost, levels, types, ...patch });

  const group = (label, options, selected, onToggle, isDisabled = () => false) => (
    <div role="group" aria-label={label} className="filter-group">
      <span className="card-label">{label}</span>
      {options.map(([key, text]) => (
        <FilterChip
          key={key}
          pressed={selected.length === 0 || selected.includes(key)}
          disabled={disabled || isDisabled(key)}
          onClick={() => onToggle(key)}
        >
          {text}
        </FilterChip>
      ))}
    </div>
  );

  return (
    <div className="filters">
      {group(
        "Cost",
        COST_OPTIONS,
        costs,
        (key) => {
          const next = toggled(costs, ["free", "paid"], key);
          change({ cost: next.length === 1 ? next[0] : "any" });
        },
        (key) => freeOnly && key === "paid",
      )}
      {group("Level", LEVEL_OPTIONS, levels, (key) => change({ levels: toggled(levels, levelKeys, key) }))}
      {group("Type", TYPE_OPTIONS, types, (key) => change({ types: toggled(types, typeKeys, key) }))}
      {freeOnly && <p className="muted">Your budget is free only, so paid resources are never listed.</p>}
    </div>
  );
}
