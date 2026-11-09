import {
  CartesianGrid, Legend, Line, LineChart, PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { TARGET_LEVELS } from "../capabilities.js";

// Recharts draws SVG attributes, which can't use CSS variables, so the token values are read once per render.
function tokens() {
  const style = getComputedStyle(document.documentElement);
  const get = (name) => style.getPropertyValue(name).trim();
  return {
    primary: get("--color-primary"),
    accent: get("--color-accent"),
    grid: get("--color-border"),
    text: get("--color-text"),
    muted: get("--color-text-muted"),
    surface: get("--color-surface"),
  };
}

const TOP = TARGET_LEVELS.length - 1;
const tooltipStyle = (t) => ({
  contentStyle: { background: t.surface, border: `1px solid ${t.grid}`, borderRadius: 10, color: t.text },
  labelStyle: { color: t.text },
});

function shorten(text, n = 22) {
  return text.length > n ? `${text.slice(0, n - 1)}…` : text;
}

// Today against target per plan gap, on the level scale (None … Expert). `points`: [{skill, today, target}].
export function SkillRadar({ points }) {
  const t = tokens();
  const data = points.map((p) => ({ ...p, label: shorten(p.skill) }));
  const summary = points
    .map((p) => `${p.skill}: ${TARGET_LEVELS[Math.floor(p.today)]} today, target ${TARGET_LEVELS[p.target]}`)
    .join("; ");
  return (
    <div className="chart" role="img" aria-label={`Radar chart of your plan's skills, today against target. ${summary}`}>
      <ResponsiveContainer width="100%" height={300}>
        <RadarChart data={data} outerRadius="70%">
          <PolarGrid stroke={t.grid} />
          <PolarAngleAxis dataKey="label" tick={{ fill: t.text, fontSize: 12 }} />
          <PolarRadiusAxis domain={[0, TOP]} tickCount={TOP + 1} tick={false} axisLine={false} />
          <Radar name="Target" dataKey="target" stroke={t.muted} strokeDasharray="5 4" fill="none" isAnimationActive={false} />
          <Radar name="Today" dataKey="today" stroke={t.primary} fill={t.primary} fillOpacity={0.25} isAnimationActive={false} />
          <Tooltip {...tooltipStyle(t)} formatter={(v, name) => [TARGET_LEVELS[Math.floor(v)], name]} />
          <Legend wrapperStyle={{ color: t.text, fontSize: 13 }} />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}

// Readiness by plan week: what was recorded so far (solid) and where the plan leads (dashed).
// `history`: [{week, score}], `planned`: scores for weeks 0-26.
export function ReadinessTrend({ history, planned }) {
  const t = tokens();
  const rows = new Map(planned.map((score, week) => [week, { week, planned: score }]));
  for (const p of history) {
    if (p.week == null) continue;
    const week = Math.round(p.week * 100) / 100;
    rows.set(week, { ...(rows.get(week) || { week }), actual: p.score });
  }
  const data = [...rows.values()].sort((a, b) => a.week - b.week);
  const last = history[history.length - 1];
  const label = `Line chart of your readiness score by plan week${last ? `: ${last.score}% now` : ""}, planned to reach ${planned[planned.length - 1]}% by week ${planned.length - 1} if you follow the plan.`;
  return (
    <div className="chart" role="img" aria-label={label}>
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: -16 }}>
          <CartesianGrid stroke={t.grid} vertical={false} />
          <XAxis
            dataKey="week" type="number" domain={[0, planned.length - 1]} ticks={[0, 4, 8, 13, 17, 21, 26]}
            tickFormatter={(w) => (w === 0 ? "Start" : `W${w}`)} tick={{ fill: t.muted, fontSize: 12 }} stroke={t.grid}
          />
          <YAxis domain={[0, 100]} ticks={[0, 50, 100]} tick={{ fill: t.muted, fontSize: 12 }} stroke={t.grid} />
          <Tooltip {...tooltipStyle(t)} labelFormatter={(w) => (w === 0 ? "Start" : `Week ${w}`)} formatter={(v, name) => [`${v}%`, name]} />
          <Legend wrapperStyle={{ color: t.text, fontSize: 13 }} />
          <Line name="Planned" dataKey="planned" stroke={t.muted} strokeDasharray="5 4" dot={false} connectNulls isAnimationActive={false} />
          <Line name="Readiness so far" dataKey="actual" stroke={t.primary} strokeWidth={2} dot={{ r: 4, fill: t.primary }} connectNulls isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
