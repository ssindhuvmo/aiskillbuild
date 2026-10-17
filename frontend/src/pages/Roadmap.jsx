import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { downloadRoadmap, generateRoadmap, getRoadmap } from "../api.js";
import Button from "../components/Button.jsx";
import Card from "../components/Card.jsx";
import MetricCard from "../components/MetricCard.jsx";
import Notice from "../components/Notice.jsx";
import PageHeader from "../components/PageHeader.jsx";
import Progress from "../components/Progress.jsx";
import ProgressBar from "../components/ProgressBar.jsx";
import { Milestone, Month, Phase, TaskRow, Week } from "../components/Timeline.jsx";

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

// Hours per task kind, summed from the saved plan (display only; the backend owns the budget).
function hoursByKind(roadmap) {
  const total = { learn: 0, practice: 0, project: 0 };
  for (const month of roadmap.months) for (const week of month.weeks) for (const task of week.tasks) total[task.kind] += task.hours;
  return total;
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

  const plain = (children) => (
    <>
      <PageHeader title="Learning Roadmap" subtitle="Six months, three phases, a portfolio project in each." />
      {children}
    </>
  );

  if (loadError) return plain(<Card><p className="error" role="alert">{loadError}</p></Card>);
  if (!state) return plain(<Card><p>Loading…</p></Card>);
  if (running) {
    return plain(<Progress messages={progressMessages(state.profile)} note="This usually takes 30–90 seconds." interval={9000} />);
  }

  const { profile, roadmap } = state;

  if (state.status === "none") {
    return plain(
      <Card>
        {error && <p className="error" role="alert">{error}</p>}
        {state.list_approved ? (
          <div className="row"><Button onClick={run}>Build my roadmap</Button></div>
        ) : (
          <p>Approve your resource list on the <Link to="/resources">Resources</Link> step first, then come back here.</p>
        )}
      </Card>
    );
  }

  const kinds = hoursByKind(roadmap);
  const free = roadmap.budget_hours - roadmap.total_hours;

  return (
    <>
      <PageHeader
        title="Learning Roadmap"
        subtitle={`${profile.current_role} → ${profile.target_role} · ${roadmap.weeks} weeks at up to ${roadmap.hours_per_week} hrs/week`}
        actions={
          <>
            <Button onClick={() => downloadRoadmap().catch((e) => setError(e.message))}>Download Plan</Button>
            <Button variant="secondary" onClick={run} disabled={!state.list_approved}>Regenerate Roadmap</Button>
          </>
        }
      />

      {state.stale && (
        <Notice>
          {state.list_approved ? (
            <>
              Your approved resources changed since this roadmap was built.{" "}
              <Button variant="text" onClick={run}>Rebuild the roadmap</Button> to update it.
            </>
          ) : (
            <>
              Your profile, skill gaps or resources changed. Approve your list on the{" "}
              <Link to="/resources">Resources</Link> step, then rebuild this roadmap.
            </>
          )}
        </Notice>
      )}
      {error && <p className="error" role="alert">{error}</p>}

      <Card title="Where your hours go">
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
      </Card>

      {roadmap.phases.map((phase) => (
        <Phase key={phase.number} title={`Phase ${phase.number}: ${phase.name}`} meta={`months ${phase.months.join("–")}`}>
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
                <Week key={week.number} title={`Week ${week.number} · ${week.focus}`} meta={`${week.hours} h`}>
                  {week.tasks.map((task, i) => (
                    <TaskRow key={i} kind={task.kind} title={task.title} hours={task.hours} link={task.resource} />
                  ))}
                </Week>
              ))}
              <Milestone>{month.milestone}</Milestone>
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
