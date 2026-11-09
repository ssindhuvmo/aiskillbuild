import { PRIORITY_KIND, STATUS, STATUS_KIND, formatDay } from "../tracking.js";
import Icon from "./Icon.jsx";
import SkillBadge from "./SkillBadge.jsx";

// The roadmap timeline: Phase > Month (collapsible) > Week > TaskRow, with a Milestone per month.
// Tracking (status, priority, due dates) comes from the backend; checkboxes call `onToggle(done)`.

export function Phase({ title, meta, status, priority, children }) {
  return (
    <section className="phase">
      <div className="phase-head">
        <h2>{title}</h2>
        <span className="phase-meta">
          <span className="muted">{meta}</span>
          {status && status !== "not_started" && <SkillBadge kind={STATUS_KIND[status] || "plain"}>{STATUS[status]}</SkillBadge>}
          {priority && <SkillBadge kind={PRIORITY_KIND[priority]}>{priority[0].toUpperCase() + priority.slice(1)} priority</SkillBadge>}
        </span>
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

// `tracking`: { status, due } for the week.
export function Week({ title, meta, tracking, children }) {
  return (
    <div className="week">
      <div className="week-head">
        <h3>{title}</h3>
        <span className={`week-status status-${tracking?.status ?? "none"}`}>
          {tracking && tracking.status !== "empty" && `${STATUS[tracking.status]} · due ${formatDay(tracking.due)} · `}
          {meta}
        </span>
      </div>
      <ul className="tasks">{children}</ul>
    </div>
  );
}

const KIND = { learn: "Learn", practice: "Practice", project: "Project" };

// One checkable row. The checkbox's 44 px target wraps the box; the text is its label.
function Check({ id, done, onToggle, busy, children }) {
  return (
    <>
      <span className="check-target">
        <input id={id} type="checkbox" checked={done} disabled={busy || !onToggle} onChange={(e) => onToggle(e.target.checked)} />
      </span>
      {children}
    </>
  );
}

// `link` ({ url, title, provider }) is the approved resource the task uses, if any. `tracking` is
// { done, status, priority } for the task.
export function TaskRow({ id, kind, title, hours, link, tracking, onToggle, busy }) {
  const inputId = `task-${id}`;
  return (
    <li className={`task${tracking?.done ? " task-done" : ""}`}>
      <Check id={inputId} done={!!tracking?.done} onToggle={onToggle} busy={busy}>
        <span className="task-body">
          <label htmlFor={inputId}>
            <span className={`task-kind kind-${kind}`}>{KIND[kind]}</span> · {title}
          </label>
          {link && (
            <>
              {" · "}
              <a href={link.url} target="_blank" rel="noopener noreferrer">{link.title} ↗</a>{" "}
              <span className="muted">{link.provider}</span>
            </>
          )}
          {tracking?.status === "overdue" && <span className="task-overdue"> · Overdue</span>}
        </span>
      </Check>
      <span className="task-hours">{hours} h</span>
    </li>
  );
}

// `tracking` is { done, status, due } for the month's milestone.
export function Milestone({ id, tracking, onToggle, busy, children }) {
  const inputId = `milestone-${id}`;
  return (
    <div className={`milestone${tracking?.done ? " task-done" : ""}`}>
      {tracking ? (
        <Check id={inputId} done={tracking.done} onToggle={onToggle} busy={busy}>
          <label htmlFor={inputId} className="milestone-text">
            <strong>Milestone</strong>
            <span className="muted"> · {tracking.done ? "Done" : `due ${formatDay(tracking.due)}`}{tracking.status === "overdue" && " · Overdue"}</span>
            <br />
            {children}
          </label>
        </Check>
      ) : (
        <>
          <Icon name="roadmap" size={20} />
          <div><strong>Milestone:</strong> {children}</div>
        </>
      )}
    </div>
  );
}
