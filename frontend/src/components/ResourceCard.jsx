import Button from "./Button.jsx";

const LEVEL_FOR = { None: "beginner", Beginner: "beginner", Intermediate: "intermediate", Experienced: "advanced" };

// One-line explanation of the ranking, built from the score breakdown.
function whyThis(item, profile) {
  const { resource: r, breakdown: b, matched_on } = item;
  const parts = [`Matches ${matched_on.join(", ")}`];
  if (b.level === 1) parts.push(`right level for ${profile.ai_level === "None" ? "a new learner" : `${profile.ai_level} AI level`}`);
  else if (r.level !== LEVEL_FOR[profile.ai_level]) parts.push(`${r.level} level — a stretch or a refresher`);
  if (b.domain === 1) parts.push(`${profile.domain}-specific`);
  if (b.time < 1) parts.push("longer than this gap needs; pick the relevant parts");
  return parts.join(" · ");
}

const capital = (s) => s.charAt(0).toUpperCase() + s.slice(1);

export default function ResourceCard({ item, profile, onRemove, disabled }) {
  const r = item.resource;
  const web = item.source === "web";
  return (
    <article className="card resource">
      <div className="card-head">
        <a className="resource-title" href={r.url} target="_blank" rel="noopener noreferrer">{r.title} ↗</a>
        <span className={`pill${web ? " pill-web" : ""}`} title={web ? "Found by live web search; the link was checked" : "From our curated library"}>
          {web ? "Web" : "Curated"}
        </span>
      </div>
      <div className="resource-meta">
        <span>{r.provider}</span>
        <span>{capital(r.format)}</span>
        <span>{r.hours} h</span>
        <span>{capital(r.level)}</span>
        <span>{capital(r.cost)}</span>
        {r.domains.map((d) => <span key={d}>{d}</span>)}
      </div>
      <p>{r.description}</p>
      <p><span className="muted">Why this:</span> {whyThis(item, profile)}</p>
      {item.also_covers.length > 0 && <p className="muted">Also covers: {item.also_covers.join(", ")}</p>}
      <Button variant="quiet" disabled={disabled} onClick={() => onRemove(r.id)} aria-label={`Remove ${r.title} from my list`}>
        Remove
      </Button>
    </article>
  );
}
