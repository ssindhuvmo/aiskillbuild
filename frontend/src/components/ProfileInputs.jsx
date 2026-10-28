import { useId } from "react";
import { BUDGETS, CAPABILITY_AREAS, CONSTRAINT_FLAGS, LEVELS, PREFERENCES } from "../capabilities.js";
import FilterChip from "./FilterChip.jsx";

// Inputs for the structured Career Profile answers, shared by the intake widgets and the
// Profile Card's edit form. Each is controlled: the parent owns the value.

// One row of level chips per capability area. onRate(area, level).
export function CapabilityRatings({ value, onRate, disabled }) {
  return (
    <div className="ratings">
      {Object.entries(CAPABILITY_AREAS).map(([area, label]) => (
        <div key={area} className="rating">
          <div className="rating-label">{label}</div>
          <div className="chips" role="group" aria-label={`${label} level`}>
            {LEVELS.map((level) => (
              <FilterChip key={level} pressed={value?.[area] === level} disabled={disabled} onClick={() => onRate(area, level)}>
                {level}
              </FilterChip>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

const toggle = (list, item) => (list.includes(item) ? list.filter((x) => x !== item) : [...list, item]);

export function PreferenceChips({ value, onChange, disabled }) {
  return (
    <div className="chips" role="group" aria-label="Learning preferences">
      {Object.entries(PREFERENCES).map(([key, label]) => (
        <FilterChip key={key} pressed={value.includes(key)} disabled={disabled} onClick={() => onChange(toggle(value, key))}>
          {label}
        </FilterChip>
      ))}
    </div>
  );
}

// value: the constraints object ({} = none).
export function ConstraintsInput({ value, onChange, disabled }) {
  const id = useId();
  const set = (patch) => onChange({ ...value, ...patch });
  return (
    <div className="stack-tight">
      <div className="chips" role="group" aria-label="Budget">
        {Object.entries(BUDGETS).map(([key, label]) => (
          <FilterChip key={key} pressed={value.budget === key} disabled={disabled}
            onClick={() => set({ budget: value.budget === key ? undefined : key })}>
            {label}
          </FilterChip>
        ))}
      </div>
      {value.budget === "monthly" && (
        <label className="field" htmlFor={`${id}-amount`}>Monthly budget (whole number)
          <input id={`${id}-amount`} type="number" min="1" value={value.monthly_budget ?? ""} disabled={disabled}
            onChange={(e) => set({ monthly_budget: e.target.value })} />
        </label>
      )}
      <div className="chips" role="group" aria-label="Constraints">
        {Object.entries(CONSTRAINT_FLAGS).map(([key, label]) => (
          <FilterChip key={key} pressed={!!value[key]} disabled={disabled} onClick={() => set({ [key]: !value[key] })}>
            {label}
          </FilterChip>
        ))}
      </div>
      <label className="field" htmlFor={`${id}-other`}>Anything else (optional)
        <input id={`${id}-other`} value={value.other ?? ""} maxLength={300} disabled={disabled}
          onChange={(e) => set({ other: e.target.value })} />
      </label>
    </div>
  );
}

// Drops unset keys so the backend sees only real choices.
export function cleanConstraints(c) {
  const out = {};
  if (c.budget) out.budget = c.budget;
  if (c.budget === "monthly") out.monthly_budget = c.monthly_budget;
  for (const k of Object.keys(CONSTRAINT_FLAGS)) if (c[k]) out[k] = true;
  if (c.other?.trim()) out.other = c.other.trim();
  return out;
}
