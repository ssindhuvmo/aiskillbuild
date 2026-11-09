import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getDashboard } from "../api.js";
import Button from "../components/Button.jsx";
import Card from "../components/Card.jsx";
import { ReadinessTrend, SkillRadar } from "../components/Charts.jsx";
import MetricCard from "../components/MetricCard.jsx";
import NextSteps from "../components/NextSteps.jsx";
import PageHeader from "../components/PageHeader.jsx";
import ProgressBar from "../components/ProgressBar.jsx";
import { TARGET_LEVELS } from "../capabilities.js";
import { formatDay } from "../tracking.js";

const PLAN_STATUS = {
  not_built: "No roadmap yet",
  not_started: "Starts soon",
  on_track: "On track",
  behind: "Behind",
  complete: "Plan complete",
};

function change(n) {
  if (n == null) return "Recorded as you report progress";
  if (n === 0) return "No change this week";
  return `${n > 0 ? "Up" : "Down"} ${Math.abs(n)} point${Math.abs(n) === 1 ? "" : "s"} this week`;
}

function timeLeft(s) {
  if (s.weeks_left == null) return "Build your roadmap";
  if (s.plan_status === "not_started") return `26 weeks from ${formatDay(s.start_date)}`;
  if (s.weeks_left === 0) return `Plan ended ${formatDay(s.end_date)}`;
  return `${s.weeks_left} week${s.weeks_left === 1 ? "" : "s"} left`;
}

function subtitle(s) {
  if (s.current_week) return `Week ${s.current_week} of 26 · your journey at a glance`;
  return "Your journey at a glance";
}

export default function Dashboard() {
  const [state, setState] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    getDashboard().then((s) => !cancelled && setState(s)).catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, []);

  const header = (sub) => (
    <PageHeader title="Dashboard" subtitle={sub} actions={<Button variant="secondary" to="/report">View Transition Report</Button>} />
  );

  if (error) return <>{header("Your journey at a glance")}<Card><p className="error" role="alert">{error}</p></Card></>;
  if (!state) return <>{header("Your journey at a glance")}<Card><p>Loading…</p></Card></>;
  if (state.status === "none") {
    return (
      <>
        {header("Your journey at a glance")}
        <Card>
          <p>Your dashboard fills in once you have a skill-gap analysis. Start on the <Link to="/gaps">Skill Analysis</Link> step.</p>
        </Card>
      </>
    );
  }

  const d = state.dashboard;
  const s = d.summary;
  const hasRoadmap = s.plan_status !== "not_built";

  return (
    <>
      {header(subtitle(s))}

      <div className="card-row card-row-narrow">
        <Card as="div"><MetricCard large label="Readiness Score" value={`${d.readiness}%`} detail={change(d.readiness_change)} /></Card>
        <Card as="div"><MetricCard large label="Skill Coverage" value={`${d.covered} of ${d.needed}`} detail="skills the role needs" /></Card>
        <Card as="div">
          <MetricCard large label="Roadmap Completion" value={`${d.completion}%`}
            detail={hasRoadmap ? `${d.done_hours} of ${d.planned_hours} planned hours` : "No roadmap yet"} />
        </Card>
        <Card as="div"><MetricCard large label="Jobs Applied" value="—" detail="Job Match comes next" /></Card>
      </div>

      <div className="split">
        <Card title="Career summary" className="split-side">
          <dl className="fields fields-grid">
            <div><dt>Current role</dt><dd>{s.current_role}</dd></div>
            <div><dt>Target role</dt><dd>{s.target_role}</dd></div>
            <div><dt>Estimated transition time</dt><dd>{timeLeft(s)}</dd></div>
            <div>
              <dt>Current status</dt>
              <dd className={`plan-status plan-${s.plan_status}`}>
                {PLAN_STATUS[s.plan_status]}
                {s.plan_status === "behind" && ` · ${s.behind_hours} h overdue`}
              </dd>
            </div>
          </dl>
          {hasRoadmap && (
            <div className="stack-tight">
              <h3>Next steps this week</h3>
              <NextSteps steps={d.next_steps} />
              <div className="row">
                <Button variant="text" to="/roadmap">Open the roadmap</Button>
                {s.plan_status === "behind" && <Button variant="text" to="/progress">Review progress</Button>}
              </div>
            </div>
          )}
          {!hasRoadmap && <p>Build your <Link to="/roadmap">Learning Roadmap</Link> to track hours and due dates.</p>}
        </Card>

        <Card title="Skill distribution" className="split-main">
          {d.radar.length >= 3 ? (
            <SkillRadar points={d.radar} />
          ) : (
            <ul className="plain-list">
              {d.radar.map((p) => (
                <li key={p.skill}>
                  <strong>{p.skill}</strong>: {TARGET_LEVELS[Math.floor(p.today)]} today, target {TARGET_LEVELS[p.target]}
                </li>
              ))}
            </ul>
          )}
          <p className="muted">Today moves toward the target as you finish roadmap work, rate your confidence and mark skills complete.</p>
        </Card>
      </div>

      {hasRoadmap && (
        <div className="split">
          <Card title="Progress trend" className="split-main">
            <ReadinessTrend history={d.history} planned={d.planned} />
            <p className="muted">
              A point is recorded each day you check off work or update your progress. The dashed line is where
              the plan takes you if you follow it.
            </p>
          </Card>
          <Card title="Milestone completion" className="split-side">
            <div className="stack">
              {d.phases.map((p) => (
                <div key={p.number} className="stack-tight">
                  <div className="row row-between">
                    <span>Phase {p.number} · {p.name}</span>
                    <span className="num">{p.percent}%</span>
                  </div>
                  <ProgressBar value={p.done_hours} max={p.planned_hours} label={`Phase ${p.number}: ${p.percent}% done`} />
                </div>
              ))}
            </div>
            {d.next_milestone && <p className="muted">Next milestone: {d.next_milestone}</p>}
          </Card>
        </div>
      )}
    </>
  );
}
