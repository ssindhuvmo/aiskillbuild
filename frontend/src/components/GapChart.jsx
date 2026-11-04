import { TARGET_LEVELS } from "../capabilities.js";

const PRIORITY_LABEL = { high: "High", medium: "Medium", low: "Low" };
const TOP = TARGET_LEVELS.length - 1;
const width = (level) => ({ width: `${(TARGET_LEVELS.indexOf(level) / TOP) * 100}%` });

// Legend for the chart: the bar is where you are, the marker where the role needs you, on the
// capability rating scale plus Expert.
export function GapLegend({ children }) {
  return (
    <div className="gap-legend">
      <span className="legend-item"><span className="legend-current" />Current</span>
      <span className="legend-item"><span className="legend-target" />Target</span>
      <span className="muted">Levels: {TARGET_LEVELS.slice(0, -1).join(", ")}, Expert (target only, beyond Experienced)</span>
      {children}
    </div>
  );
}

// One row per gap: the current level as a bar and the target as a marker, with priority and
// effort. `actions(gap)` renders the correction buttons in the last column.
export default function GapChart({ gaps, domain, actions }) {
  return (
    <div className="table-scroll">
      <table className="table">
        <thead>
          <tr>
            <th scope="col">Skill</th>
            <th scope="col" className="gap-col">Current against target</th>
            <th scope="col">Priority</th>
            <th scope="col">Effort</th>
            {actions && <th scope="col"><span className="sr-only">Corrections</span></th>}
          </tr>
        </thead>
        <tbody>
          {gaps.map((g) => (
            <tr key={g.skill}>
              <th scope="row">
                <strong>{g.skill}</strong>
                {g.domain_specific && <> <span className="pill">{domain}</span></>}
                <p className="muted">{g.why_needed}</p>
              </th>
              <td>
                <div className="gap-bar" role="img" aria-label={`Current level ${g.current_level}, target ${g.target_level}`}>
                  <span className="gap-current" style={width(g.current_level)} />
                  <span className="gap-target" style={width(g.target_level)} />
                </div>
                <div className="muted gap-levels">{g.current_level} → {g.target_level}</div>
              </td>
              <td className={`prio-${g.priority}`}>{PRIORITY_LABEL[g.priority]}</td>
              <td className="num">{g.effort_hours} h</td>
              {actions && <td>{actions(g)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
