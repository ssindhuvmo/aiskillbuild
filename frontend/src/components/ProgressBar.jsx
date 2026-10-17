// A determinate bar. Pass `value` for a single fill, or `segments` ([{ value, tone }]) for a
// stacked bar, which is described by `label` alone.
export default function ProgressBar({ value = 0, max, label, segments }) {
  const width = (n) => ({ width: `${max > 0 ? Math.min(100, (n / max) * 100) : 0}%` });
  if (segments) {
    return (
      <div className="bar" role="img" aria-label={label}>
        {segments.map((s) => <span key={s.tone} className={`bar-fill tone-${s.tone}`} style={width(s.value)} />)}
      </div>
    );
  }
  return (
    <div className="bar" role="progressbar" aria-label={label} aria-valuenow={value} aria-valuemin={0} aria-valuemax={max}>
      <span className="bar-fill tone-primary" style={width(value)} />
    </div>
  );
}
