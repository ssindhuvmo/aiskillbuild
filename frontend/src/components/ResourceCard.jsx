const LEVEL_FOR = { None: "beginner", Beginner: "beginner", Intermediate: "intermediate", Experienced: "advanced" };

// One-line explanation of the ranking, built from the score breakdown.
function whyThis(item, profile) {
  const { resource: r, breakdown: b, matched_on } = item;
  const parts = [`Matches ${matched_on.join(", ")}`];
  if (b.level === 1) parts.push(`right level for ${profile.ai_experience === "None" ? "a new learner" : `${profile.ai_experience} AI experience`}`);
  else if (r.level !== LEVEL_FOR[profile.ai_experience]) parts.push(`${r.level} level — a stretch or a refresher`);
  if (b.domain === 1) parts.push(`${profile.domain}-specific`);
  if (b.time < 1) parts.push("longer than this gap needs; pick the relevant parts");
  return parts.join(" · ");
}

export default function ResourceCard({ item, profile }) {
  const r = item.resource;
  return (
    <li className="resource">
      <div className="skill-head">
        <a href={r.url} target="_blank" rel="noopener noreferrer"><strong>{r.title}</strong></a>
        <span className="muted">{r.provider}</span>
      </div>
      <div className="skill-head">
        <span className={`tag fmt-${r.format}`}>{r.format}</span>
        <span className="tag">{r.level}</span>
        <span className={`tag ${r.cost}`}>{r.cost}</span>
        <span className="tag">{r.hours} h</span>
        {r.domains.map((d) => <span key={d} className="tag domain">{d}</span>)}
      </div>
      <p>{r.description}</p>
      <p className="muted why">Why this: {whyThis(item, profile)}</p>
      {item.also_covers.length > 0 && <p className="muted">Also covers: {item.also_covers.join(", ")}</p>}
    </li>
  );
}
