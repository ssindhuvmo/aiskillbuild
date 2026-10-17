// A label with a large value. `tone` adds the color swatch that matches a ProgressBar segment.
export default function MetricCard({ label, value, tone, large }) {
  return (
    <div className={`metric${large ? " metric-large" : ""}`}>
      <div className="metric-label">
        {tone && <span className={`swatch tone-${tone}`} />}
        {label}
      </div>
      <div className="metric-value">{value}</div>
    </div>
  );
}
