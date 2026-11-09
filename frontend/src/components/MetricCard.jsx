// A label with a large value and an optional `detail` line below. `tone` adds the color swatch that matches
// a ProgressBar segment.
export default function MetricCard({ label, value, tone, large, detail }) {
  return (
    <div className={`metric${large ? " metric-large" : ""}`}>
      <div className="metric-label">
        {tone && <span className={`swatch tone-${tone}`} />}
        {label}
      </div>
      <div className="metric-value">{value}</div>
      {detail && <div className="metric-detail">{detail}</div>}
    </div>
  );
}
