import Icon from "./Icon.jsx";

// The roadmap timeline: Phase > Month (collapsible) > Week > TaskRow, with a Milestone per month.

export function Phase({ title, meta, children }) {
  return (
    <section className="phase">
      <div className="phase-head">
        <h2>{title}</h2>
        <span className="muted">{meta}</span>
      </div>
      {children}
    </section>
  );
}

export function Month({ title, meta, summary, defaultOpen, children }) {
  return (
    <details className="month" open={defaultOpen}>
      <summary>
        <span className="month-title">{title}</span>
        <span className="month-meta">{meta}</span>
      </summary>
      {summary && <p className="month-summary">{summary}</p>}
      {children}
    </details>
  );
}

export function Week({ title, meta, children }) {
  return (
    <div className="week">
      <div className="week-head">
        <h3>{title}</h3>
        <span className="muted">{meta}</span>
      </div>
      <ul className="tasks">{children}</ul>
    </div>
  );
}

const KIND = { learn: "Learn", practice: "Practice", project: "Project" };

// `link` ({ url, title, provider }) is the approved resource the task uses, if any.
export function TaskRow({ kind, title, hours, link }) {
  return (
    <li className="task">
      <span className="task-body">
        <span className={`task-kind kind-${kind}`}>{KIND[kind]}</span> · {title}
        {link && (
          <>
            {" · "}
            <a href={link.url} target="_blank" rel="noopener noreferrer">{link.title} ↗</a>{" "}
            <span className="muted">{link.provider}</span>
          </>
        )}
      </span>
      <span className="task-hours">{hours} h</span>
    </li>
  );
}

export function Milestone({ children }) {
  return (
    <div className="milestone">
      <Icon name="roadmap" size={20} />
      <div><strong>Milestone:</strong> {children}</div>
    </div>
  );
}
