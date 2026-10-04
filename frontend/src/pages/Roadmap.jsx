import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { downloadRoadmap, generateRoadmap, getRoadmap } from "../api.js";
import Progress from "../components/Progress.jsx";

function progressMessages({ target_role: role, domain, hours_per_week: hours }) {
  return [
    `Planning your 6 months toward ${role}…`,
    "Putting your resources in the right order…",
    `Fitting each week into ${hours} hours…`,
    `Designing portfolio projects for ${domain}…`,
    "Setting a milestone for each month…",
    "Checking the plan against your hour budget…",
    "Almost there — a full roadmap takes a little while…",
  ];
}

const KIND = { learn: "Learn", practice: "Practice", project: "Project" };

// A task that uses an approved resource links to it; practice and project tasks may have none.
function Task({ task }) {
  return (
    <li>
      <span className={`tag kind-${task.kind}`}>{KIND[task.kind]}</span> {task.title}{" "}
      <span className="muted">{task.hours} h</span>
      {task.resource && (
        <div>
          <a href={task.resource.url} target="_blank" rel="noopener noreferrer">{task.resource.title} ↗</a>{" "}
          <span className="muted">{task.resource.provider}</span>
        </div>
      )}
    </li>
  );
}

export default function Roadmap() {
  const [state, setState] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const autoRan = useRef(false);

  async function run() {
    setRunning(true);
    setError("");
    try {
      setState(await generateRoadmap());
    } catch (e) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    getRoadmap()
      .then((s) => {
        if (cancelled) return;
        setState(s);
        // First visit with an approved list: build the roadmap right away.
        if (s.status === "none" && s.list_approved && !autoRan.current) {
          autoRan.current = true;
          run();
        }
      })
      .catch((e) => !cancelled && setLoadError(e.message));
    return () => {
      cancelled = true;
    };
  }, []);

  if (loadError) return <main className="card"><p className="error">{loadError}</p></main>;
  if (!state) return <main className="card"><p>Loading…</p></main>;
  if (running) {
    return <Progress messages={progressMessages(state.profile)} note="This usually takes 30–90 seconds." interval={9000} />;
  }

  const { profile, roadmap } = state;

  if (state.status === "none") {
    return (
      <main className="card">
        <h2>Roadmap</h2>
        {error && <p className="error">{error}</p>}
        {state.list_approved ? (
          <button onClick={run}>Build my roadmap</button>
        ) : (
          <p>Approve your resource list on the <Link to="/resources">Resources</Link> step first, then come back here.</p>
        )}
      </main>
    );
  }

  const phaseOf = (month) => roadmap.phases.find((p) => p.months.includes(month));

  return (
    <main className="gaps">
      {state.stale && (
        <div className="card banner">
          {state.list_approved ? (
            <>
              Your approved resources changed since this roadmap was built.{" "}
              <button className="link" onClick={run}>Rebuild the roadmap</button> to update it.
            </>
          ) : (
            <>
              Your profile, skill gaps or resources changed. Approve your list on the{" "}
              <Link to="/resources">Resources</Link> step, then rebuild this roadmap.
            </>
          )}
        </div>
      )}
      {error && <div className="card"><p className="error">{error}</p></div>}

      <section className="card">
        <h2>Your 6-month roadmap: {profile.current_role} → {profile.target_role}</h2>
        <p>
          {roadmap.weeks} weeks at up to {roadmap.hours_per_week} hrs/week. <strong>{roadmap.total_hours} hours</strong>{" "}
          planned of your {roadmap.budget_hours}-hour budget.
        </p>
        <div className="row">
          <button onClick={() => downloadRoadmap().catch((e) => setError(e.message))}>Download Markdown</button>
          <button className="secondary" onClick={run} disabled={!state.list_approved}>Rebuild</button>
        </div>
      </section>

      {roadmap.months.map((month) => {
        const phase = phaseOf(month.number);
        return (
          <div key={month.number} className="gaps">
            {phase.months[0] === month.number && (
              <h2 className="phase">Phase {phase.number}: {phase.name} <span className="muted">months {phase.months.join("–")}</span></h2>
            )}
            <details className="card month" open={month.number === 1}>
              <summary>
                <strong>Month {month.number}: {month.theme}</strong>
                <span className="muted">weeks {month.weeks[0].number}–{month.weeks[month.weeks.length - 1].number} · {month.hours} h</span>
              </summary>
              <p>{month.summary}</p>
              <ol className="weeks">
                {month.weeks.map((week) => (
                  <li key={week.number}>
                    <div className="skill-head">
                      <strong>Week {week.number}</strong>
                      <span>{week.focus}</span>
                      <span className="tag">{week.hours} h</span>
                    </div>
                    <ul className="tasks">
                      {week.tasks.map((task, i) => <Task key={i} task={task} />)}
                    </ul>
                  </li>
                ))}
              </ol>
              <p className="milestone"><strong>Milestone:</strong> {month.milestone}</p>
            </details>
            {phase.months[phase.months.length - 1] === month.number && (
              <section className="card project">
                <div className="skill-head">
                  <h2 className="inline">Portfolio project: {phase.project.title}</h2>
                  <span className="tag domain">{profile.domain}</span>
                </div>
                <p>{phase.project.problem}</p>
                <p><strong>Dataset:</strong> {phase.project.dataset}</p>
                <ul className="tasks">
                  {phase.project.deliverables.map((d) => <li key={d}>{d}</li>)}
                </ul>
              </section>
            )}
          </div>
        );
      })}

      {roadmap.unscheduled.length > 0 && (
        <section className="card">
          <h2>Approved but not scheduled</h2>
          <p className="muted">These did not fit in your {roadmap.budget_hours}-hour budget. Keep them for later.</p>
          <ul className="tasks">
            {roadmap.unscheduled.map((r) => (
              <li key={r.id}>
                <a href={r.url} target="_blank" rel="noopener noreferrer">{r.title}</a>{" "}
                <span className="muted">{r.provider} · {r.hours} h</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
