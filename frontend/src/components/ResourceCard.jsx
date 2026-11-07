import Button from "./Button.jsx";
import { PREFERENCES } from "../capabilities.js";

const LEVEL_FOR = { None: "beginner", Beginner: "beginner", Intermediate: "intermediate", Experienced: "advanced" };
const FORMAT_LABEL = {
  course: "Course", video: "Video", article: "Article", paper: "Paper", tutorial: "Tutorial",
  repository: "GitHub Repository", book: "Book", project: "Project",
};
const SOURCE = {
  knowledge_base: { label: "Curated", title: "From our curated library", className: "pill" },
  web: { label: "Web", title: "Found by live web search; the link was checked", className: "pill pill-web" },
  youtube: { label: "YouTube", title: "Found on YouTube; length, views and likes come from YouTube", className: "pill pill-web" },
};
// Which intake preferences a format satisfies (mirrors ranking.PREFERENCE_MATCH).
const MATCHES = {
  free_courses: (r) => r.format === "course" && r.cost === "free",
  paid_courses: (r) => r.format === "course" && r.cost === "paid",
  video: (r) => r.format === "video",
  articles: (r) => ["article", "paper", "tutorial"].includes(r.format),
  books: (r) => r.format === "book",
  projects: (r) => ["project", "repository"].includes(r.format),
};

const capital = (s) => s.charAt(0).toUpperCase() + s.slice(1);
const compact = new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 });

// One-line explanation of the ranking, built from the score breakdown.
function whyThis(item, profile) {
  const { resource: r, breakdown: b, matched_on } = item;
  const parts = [`Matches ${matched_on.join(", ")}`];
  if (b.level === 1) parts.push(`right level for ${profile.ai_level === "None" ? "a new learner" : `${profile.ai_level} AI level`}`);
  else if (r.level !== LEVEL_FOR[profile.ai_level]) parts.push(`${r.level} level — a stretch or a refresher`);
  if (b.domain === 1) parts.push(`${profile.domain}-specific`);
  const liked = (profile.learning_preferences || []).find((p) => MATCHES[p]?.(r));
  if (liked) parts.push(`you prefer ${PREFERENCES[liked].toLowerCase()}`);
  if (r.quality?.trusted) parts.push("from a trusted channel");
  if (b.time < 1) parts.push("longer than this gap needs; pick the relevant parts");
  return parts.join(" · ");
}

// A resource on the list. `progress` is its Save / Start / Complete record (or undefined); onProgress(change)
// sends {saved} or {status}.
export default function ResourceCard({ item, profile, progress, onRemove, onProgress, disabled }) {
  const r = item.resource;
  const source = SOURCE[item.source] || SOURCE.web;
  const saved = progress?.saved ?? false;
  const status = progress?.status ?? "not_started";
  return (
    <article className="card resource">
      <div className="card-head">
        <a className="resource-title" href={r.url} target="_blank" rel="noopener noreferrer">{r.title} ↗</a>
        <span className={source.className} title={source.title}>{source.label}</span>
      </div>
      <div className="resource-meta">
        <span>{r.provider}</span>
        <span>{FORMAT_LABEL[r.format] ?? capital(r.format)}</span>
        <span>{r.hours} h</span>
        <span>{capital(r.level)}</span>
        <span>{capital(r.cost)}</span>
        {r.quality?.views != null && <span>{compact.format(r.quality.views)} views</span>}
        {r.quality?.likes != null && <span>{compact.format(r.quality.likes)} likes</span>}
        {r.domains.map((d) => <span key={d}>{d}</span>)}
      </div>
      <p>{r.description}</p>
      <p><span className="muted">Why this:</span> {whyThis(item, profile)}</p>
      {item.also_covers.length > 0 && <p className="muted">Also covers: {item.also_covers.join(", ")}</p>}
      <ProgressButtons title={r.title} saved={saved} status={status} onProgress={onProgress} />
      <Button variant="quiet" disabled={disabled} onClick={() => onRemove(r.id)} aria-label={`Remove ${r.title} from my list`}>
        Remove
      </Button>
    </article>
  );
}

// Save / Start / Complete (self-reported). Each is a toggle; they never change the list.
export function ProgressButtons({ title, saved, status, onProgress, busy }) {
  return (
    <div className="row progress-buttons">
      <Button variant="secondary" aria-pressed={saved} disabled={busy} onClick={() => onProgress({ saved: !saved })}
        aria-label={`${saved ? "Unsave" : "Save"} ${title}`}>
        {saved ? "Saved" : "Save"}
      </Button>
      <Button variant="secondary" aria-pressed={status === "started"} disabled={busy}
        onClick={() => onProgress({ status: status === "started" ? "not_started" : "started" })}
        aria-label={`${status === "started" ? "Mark not started" : "Start"} ${title}`}>
        {status === "started" ? "Started" : "Start"}
      </Button>
      <Button variant="secondary" aria-pressed={status === "completed"} disabled={busy}
        onClick={() => onProgress({ status: status === "completed" ? "started" : "completed" })}
        aria-label={`${status === "completed" ? "Mark not complete" : "Complete"} ${title}`}>
        {status === "completed" ? "Completed ✓" : "Complete"}
      </Button>
    </div>
  );
}
