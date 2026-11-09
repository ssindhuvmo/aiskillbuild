import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { downloadRoadmap, generateRoadmap, getRoadmap, setRoadmapItem, setStartDate } from "../api.js";
import Button from "../components/Button.jsx";
import Card from "../components/Card.jsx";
import MetricCard from "../components/MetricCard.jsx";
import Notice from "../components/Notice.jsx";
import PageHeader from "../components/PageHeader.jsx";
import Progress from "../components/Progress.jsx";
import ProgressBar from "../components/ProgressBar.jsx";
import { Milestone, Month, Phase, TaskRow, Week } from "../components/Timeline.jsx";
import { formatDay } from "../tracking.js";

function progressMessages({ target_role: role, hours_per_week: hours }) {
  return [`Planning your 6 months toward ${role}…`, `Fitting each week into ${hours} hours…`];
}

// What a phase shows while its text is written, or after the AI's text couldn't be used.
const NARRATIVE_NOTE = {
  pending: "Writing this phase's names, milestones and portfolio project…",
  default: "This phase shows plain text because the AI's descriptions weren't available. Regenerate to try again.",
};

// Hours per task kind, summed from the saved plan (display only; the backend owns the budget).
function hoursByKind(roadmap) {
  const total = { learn: 0, practice: 0, project: 0 };
  for (const month of roadmap.months) for (const week of month.weeks) for (const task of week.tasks) total[task.kind] += task.hours;
  return total;
}

export default function Roadmap() {
  const [state, setState] = useState(null);
  const [building, setBuilding] = useState(false); // first build: nothing to show until the plan arrives
  const [lastRun, setRun] = useState(null); // this visit's last run: { written: phases with text, done, at }
  const [error, setError] = useState("");
  const [notices, setNotices] = useState([]);
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState(null); // the item id (or "start") being saved
  const autoRan = useRef(false);

  // Shows the tick at once; the server's reply (statuses, next steps) replaces it, or it is put back.
  async function toggle(id, done) {
    const before = state;
    setState((s) => ({
      ...s,
      tracking: { ...s.tracking, items: { ...s.tracking.items, [id]: { ...s.tracking.items[id], done } } },
    }));
    setBusy(id);
    setError("");
    try {
      setState(await setRoadmapItem(id, done));
    } catch (e) {
      setState(before);
      setError(e.message);
    } finally {
      setBusy(null);
    }
  }

  async function changeStart(value) {
    if (!value) return;
    setBusy("start");
    setError("");
    try {
      setState(await setStartDate(value));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  }

  // The placed plan arrives first; each phase's text follows as it is written. A regenerate keeps the page
  // on screen and reports progress in a banner, because the weeks usually come back unchanged.
  async function run(hasRoadmap) {
    setBuilding(!hasRoadmap);
    setError("");
    setNotices([]);
    setRun({ written: 0, done: false });
    let written = 0;
    await generateRoadmap({
      onState: ({ state: next, notice, phase }) => {
        setState(next);
        setBuilding(false);
        if (phase) setRun({ written: ++written, done: false });
        if (notice) setNotices((list) => [...list, notice]);
      },
      onError: (message) => {
        setError(message);
        setRun(null);
      },
    });
    setBuilding(false);
    setRun((r) => r && { ...r, done: true, at: new Date() });
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
          run(false);
        }
      })
      .catch((e) => !cancelled && setLoadError(e.message));
    return () => {
      cancelled = true;
    };
  }, []);

  const plain = (children) => (
    <>
      <PageHeader title="Learning Roadmap" subtitle="Six months, three phases, a portfolio project in each." />
      {children}
    </>
  );

  if (loadError) return plain(<Card><p className="error" role="alert">{loadError}</p></Card>);
  if (!state) return plain(<Card><p>Loading…</p></Card>);
  if (building) {
    return plain(<Progress messages={progressMessages(state.profile)} note="This takes a few seconds." interval={3000} />);
  }

  const { profile, roadmap } = state;

  if (state.status === "none") {
    return plain(
      <Card>
        {error && <p className="error" role="alert">{error}</p>}
        {state.list_approved ? (
          <div className="row"><Button onClick={() => run(false)}>Build my roadmap</Button></div>
        ) : (
          <p>Approve your resource list on the <Link to="/resources">Resources</Link> step first, then come back here.</p>
        )}
      </Card>
    );
  }

  const kinds = hoursByKind(roadmap);
  const free = roadmap.budget_hours - roadmap.total_hours;
  const writing = roadmap.phases.some((p) => p.narrative === "pending") || (lastRun && !lastRun.done);
  const tracking = state.tracking;
  const items = tracking.items;
  const weekTracking = Object.fromEntries(tracking.weeks.map((w) => [w.number, w]));
  const phaseTracking = Object.fromEntries(tracking.phases.map((p) => [p.number, p]));
  const download = (format) => downloadRoadmap(format).catch((e) => setError(e.message));

  return (
    <>
      <PageHeader
        title="Learning Roadmap"
        subtitle={`${profile.current_role} → ${profile.target_role} · ${roadmap.weeks} weeks at up to ${roadmap.hours_per_week} hrs/week · started ${formatDay(state.start_date, true)}`}
        actions={
          <>
            <Button onClick={() => download("md")}>Download Plan</Button>
            <Button variant="secondary" onClick={() => download("pdf")}>Export PDF</Button>
            <Button variant="secondary" onClick={() => run(true)} disabled={!state.list_approved || writing}>
              {writing ? "Regenerating…" : "Regenerate Roadmap"}
            </Button>
            <Button variant="secondary" to="/report">View Transition Report</Button>
          </>
        }
      />

      {state.stale && (
        <Notice>
          {state.list_approved ? (
            <>
              Your approved resources changed since this roadmap was built.{" "}
              <Button variant="text" onClick={() => run(true)}>Rebuild the roadmap</Button> to update it.
            </>
          ) : (
            <>
              Your profile, skill gaps or resources changed. Approve your list on the{" "}
              <Link to="/resources">Resources</Link> step, then rebuild this roadmap.
            </>
          )}
        </Notice>
      )}
      {lastRun && (
        <Notice>
          {lastRun.done ? (
            <>
              Roadmap regenerated at {lastRun.at.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}. The
              phase names, milestones, practice tasks and portfolio projects were rewritten. The weeks and hours are
              planned from your approved resources and weekly hours, so they stay the same unless those change.
            </>
          ) : (
            <>
              Regenerating your roadmap… The weekly plan is ready; writing each phase's text ({lastRun.written} of{" "}
              {roadmap.phases.length} done).
            </>
          )}
        </Notice>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      {notices.map((n) => <Notice key={n}>{n}</Notice>)}

      <div className="split">
      <Card title="Where your hours go" className="split-main">
        <ProgressBar
          max={roadmap.budget_hours}
          label={`${kinds.learn} hours learning, ${kinds.practice} practice, ${kinds.project} project, ${free} free, of ${roadmap.budget_hours}`}
          segments={[
            { value: kinds.learn, tone: "primary" },
            { value: kinds.practice, tone: "accent" },
            { value: kinds.project, tone: "soft" },
          ]}
        />
        <div className="metrics">
          <MetricCard label="Learn" value={`${kinds.learn} h`} tone="primary" />
          <MetricCard label="Practice" value={`${kinds.practice} h`} tone="accent" />
          <MetricCard label="Project" value={`${kinds.project} h`} tone="soft" />
          <MetricCard label="Planned" value={`${roadmap.total_hours} h`} />
          <MetricCard label={`Free in your ${roadmap.budget_hours} h budget`} value={`${free} h`} />
        </div>
        <h3>Your progress</h3>
        <ProgressBar
          value={tracking.done_tasks}
          max={tracking.total_tasks}
          label={`${tracking.done_tasks} of ${tracking.total_tasks} tasks done`}
        />
        <p className="muted">
          {tracking.done_tasks} of {tracking.total_tasks} tasks done · {tracking.done_hours} of {tracking.planned_hours} hours
        </p>
      </Card>

      <Card title="Immediate next steps" className="split-side">
        {tracking.next_steps.length ? (
          <ol className="next-steps">
            {tracking.next_steps.map((step) => (
              <li key={step.task_id}>
                <span>
                  {step.title}
                  {step.resource && (
                    <>
                      {" · "}
                      <a href={step.resource.url} target="_blank" rel="noopener noreferrer">{step.resource.title} ↗</a>
                    </>
                  )}
                </span>
                <span className={step.overdue ? "next-step-meta overdue" : "next-step-meta"}>
                  {step.hours} h · {step.overdue ? `overdue since ${formatDay(step.due)}` : `week ${step.week}, due ${formatDay(step.due)}`}
                </span>
              </li>
            ))}
          </ol>
        ) : (
          <p>Every task is done. Well done!</p>
        )}
        <label className="field">
          Start date (week 1 begins)
          <input
            type="date"
            value={state.start_date}
            disabled={busy === "start"}
            onChange={(e) => changeStart(e.target.value)}
          />
        </label>
      </Card>
      </div>

      {roadmap.phases.map((phase) => (
        <Phase
          key={phase.number}
          title={`Phase ${phase.number}: ${phase.name}`}
          meta={`months ${phase.months.join("–")}`}
          status={phaseTracking[phase.number]?.status}
          priority={phaseTracking[phase.number]?.priority}
        >
          {NARRATIVE_NOTE[phase.narrative] && (
            <p className="muted" role="status">{NARRATIVE_NOTE[phase.narrative]}</p>
          )}
          <Card as="div" className="project">
            <div className="stack-tight">
              <div className="card-label">Portfolio project · {profile.domain}</div>
              <h3>{phase.project.title}</h3>
              <p>{phase.project.problem}</p>
              <p className="muted">Dataset: {phase.project.dataset}</p>
            </div>
            <div className="stack-tight">
              <div className="muted">Deliverables</div>
              <ul className="plain-list">
                {phase.project.deliverables.map((d) => <li key={d}>{d}</li>)}
              </ul>
            </div>
          </Card>

          {roadmap.months.filter((m) => phase.months.includes(m.number)).map((month) => (
            <Month
              key={month.number}
              title={`Month ${month.number}: ${month.theme}`}
              meta={`weeks ${month.weeks[0].number}–${month.weeks[month.weeks.length - 1].number} · ${month.hours} h`}
              summary={month.summary}
              defaultOpen={month.number === 1}
            >
              {month.weeks.map((week) => (
                <Week key={week.number} title={`Week ${week.number} · ${week.focus}`} meta={`${week.hours} h`} tracking={weekTracking[week.number]}>
                  {week.tasks.map((task, i) => {
                    const id = task.id || `w${week.number}-${i + 1}`; // same fallback as tracking.task_id
                    return (
                      <TaskRow
                        key={id}
                        id={id}
                        kind={task.kind}
                        title={task.title}
                        hours={task.hours}
                        link={task.resource}
                        tracking={items[id]}
                        busy={busy === id}
                        onToggle={(done) => toggle(id, done)}
                      />
                    );
                  })}
                  {week.tasks.length === 0 && <li className="task muted">Nothing planned: catch up or rest.</li>}
                </Week>
              ))}
              <Milestone
                id={`m${month.number}`}
                tracking={items[`m${month.number}`]}
                busy={busy === `m${month.number}`}
                onToggle={(done) => toggle(`m${month.number}`, done)}
              >
                {month.milestone}
              </Milestone>
            </Month>
          ))}
        </Phase>
      ))}

      {roadmap.unscheduled.length > 0 && (
        <Card title="Approved but not scheduled">
          <p className="muted">These did not fit in your {roadmap.budget_hours}-hour budget. Keep them for later.</p>
          <ul className="plain-list">
            {roadmap.unscheduled.map((r) => (
              <li key={r.id}>
                <a href={r.url} target="_blank" rel="noopener noreferrer">{r.title} ↗</a>{" "}
                <span className="muted">{r.provider} · {r.hours} h</span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}
