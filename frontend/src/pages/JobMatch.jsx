import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getJobs, markJob, searchJobs } from "../api.js";
import Button from "../components/Button.jsx";
import Card from "../components/Card.jsx";
import FilterChip from "../components/FilterChip.jsx";
import Notice from "../components/Notice.jsx";
import PageHeader from "../components/PageHeader.jsx";
import Progress from "../components/Progress.jsx";
import ProgressBar from "../components/ProgressBar.jsx";
import SkillBadge from "../components/SkillBadge.jsx";

const SEARCH_MESSAGES = [
  "Searching the job sites…",
  "Checking that each posting's link works…",
  "Comparing each role's required skills with yours…",
];
// Salary filter: annual amounts in the posting's own currency, parsed by the backend from the stated salary.
const SALARY = [
  { value: "any", label: "Any" },
  { value: "stated", label: "Salary stated" },
  { value: "50000", label: "At least 50k a year" },
  { value: "100000", label: "At least 100k a year" },
  { value: "150000", label: "At least 150k a year" },
];
const MODE = { remote: "Remote", hybrid: "Hybrid", onsite: "On-site", unknown: "" };

function keepBySalary(view, salary) {
  const { salary_min: low, salary_max: high } = view.job;
  if (salary === "any") return true;
  if (salary === "stated") return Boolean(view.job.salary);
  return (high ?? low ?? 0) >= Number(salary);
}

function foundOn(iso) {
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function place(job) {
  return [job.location, MODE[job.work_mode]].filter(Boolean).join(" · ");
}

function JobDetail({ view, busy, onMark }) {
  const { job } = view;
  const total = job.required_skills.length;
  return (
    <Card as="aside" className="split-side job-detail" aria-label="Job details">
      <div className="stack-tight">
        <h2>{job.title}</h2>
        <div>{[job.company, place(job), job.experience].filter(Boolean).join(" · ")}</div>
        <a href={job.url} target="_blank" rel="noopener noreferrer">View the original posting ↗</a>
        {job.link === "blocked" && (
          <span className="muted">Link not checked: this site blocks automated checks. Found {foundOn(job.found_on)}.</span>
        )}
      </div>
      <div className="stack-tight">
        <div className="card-label">Job description</div>
        <p>{job.summary}</p>
      </div>
      <div className="stack-tight">
        <div className="card-label">Required skills you have · {view.have.length} of {total}</div>
        {view.have.length ? (
          <div className="chips">{view.have.map((s) => <SkillBadge key={s} kind="skill">{s}</SkillBadge>)}</div>
        ) : (
          <p className="muted">None yet.</p>
        )}
      </div>
      {view.missing.length > 0 && (
        <div className="stack-tight">
          <div className="card-label">Missing skills</div>
          <div className="chips">{view.missing.map((m) => <SkillBadge key={m.skill} kind="gap">{m.skill}</SkillBadge>)}</div>
          {view.missing.some((m) => m.in_plan) && (
            <p className="muted">
              In your plan:{" "}
              {view.missing.filter((m) => m.in_plan).map((m) => `${m.skill}${m.phase ? ` (phase ${m.phase})` : ""}`).join(", ")}.
            </p>
          )}
        </div>
      )}
      <div className="stack-tight">
        <div className="card-label">Match explanation</div>
        <p>{job.explanation}</p>
        {job.explained_by === "default" && <p className="muted">Matched by name only.</p>}
      </div>
      <div className="row">
        <a className="btn btn-primary" href={job.url} target="_blank" rel="noopener noreferrer">Apply ↗</a>
        <FilterChip pressed={view.applied} disabled={busy} onClick={() => onMark(job.id, { applied: !view.applied })}>
          {view.applied ? "Applied ✓" : "Mark as applied"}
        </FilterChip>
        <FilterChip pressed={view.saved} disabled={busy} onClick={() => onMark(job.id, { saved: !view.saved })}>
          {view.saved ? "Saved ✓" : "Save Job"}
        </FilterChip>
        <Button variant="secondary" to={`/resume?job=${encodeURIComponent(job.id)}`}>Update Resume</Button>
      </div>
      <p className="muted">
        Apply opens the posting in a new tab. Nothing is submitted for you; mark it as applied yourself.
      </p>
    </Card>
  );
}

function JobTable({ views, selected, onSelect, caption }) {
  return (
    <div className="table-scroll">
      <table className="table job-table">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            <th scope="col">Job Title</th>
            <th scope="col">Company</th>
            <th scope="col">Match Score</th>
            <th scope="col">Salary</th>
            <th scope="col">Experience</th>
          </tr>
        </thead>
        <tbody>
          {views.map((v) => (
            <tr key={v.job.id}>
              <th scope="row">
                <button type="button" className="link-button" aria-pressed={selected === v.job.id} onClick={() => onSelect(v.job.id)}>
                  {v.job.title}
                </button>
                {(v.saved || v.applied) && (
                  <div className="muted">{[v.applied && "Applied", v.saved && "Saved"].filter(Boolean).join(" · ")}</div>
                )}
              </th>
              <td>{v.job.company}</td>
              <td>
                <div className="score">
                  <ProgressBar value={v.score} max={100} label={`Match score ${v.score}%`} />
                  <span className="num">{v.score}%</span>
                </div>
              </td>
              <td>{v.job.salary || "Not stated"}</td>
              <td>{v.job.experience || "Not stated"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function JobMatch() {
  const [state, setState] = useState(null);
  const [query, setQuery] = useState({ location: "", remote: false, hybrid: false });
  const [salary, setSalary] = useState("any");
  const [selected, setSelected] = useState(null);
  const [searching, setSearching] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");

  function load(next) {
    setState(next);
    setQuery(next.query);
  }

  useEffect(() => {
    let cancelled = false;
    getJobs().then((s) => !cancelled && load(s)).catch((e) => !cancelled && setLoadError(e.message));
    return () => {
      cancelled = true;
    };
  }, []);

  async function search() {
    setSearching(true);
    setError("");
    try {
      const next = await searchJobs(query);
      load(next);
      setSelected(next.jobs[0]?.job.id ?? null);
    } catch (e) {
      setError(e.message);
    } finally {
      setSearching(false);
    }
  }

  async function mark(jobId, change) {
    setBusy(true);
    setError("");
    try {
      setState(await markJob(jobId, change));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const subtitle = state?.found_at
    ? `Scored against the skills you have today. Found ${foundOn(state.found_at)}.`
    : "Roles that fit the skills you have built, scored against them.";
  const header = (actions) => <PageHeader title="Job Match" subtitle={subtitle} actions={actions} />;

  if (loadError) return <>{header()}<Card><p className="error" role="alert">{loadError}</p></Card></>;
  if (!state) return <>{header()}<Card><p>Loading…</p></Card></>;
  if (!state.can_search) {
    return (
      <>
        {header()}
        <Card><p>Jobs are matched against your skills. Run your <Link to="/gaps">Skill Analysis</Link> first.</p></Card>
      </>
    );
  }

  const shown = state.jobs.filter((v) => keepBySalary(v, salary));
  const all = [...state.jobs, ...state.kept];
  const current = all.find((v) => v.job.id === selected) || shown[0] || null;
  const queryChanged = state.status === "ready" && JSON.stringify(query) !== JSON.stringify(state.query);

  return (
    <>
      {header(
        <Button onClick={search} disabled={searching}>
          {searching ? "Searching…" : state.status === "ready" && !queryChanged ? "Refresh" : "Find jobs"}
        </Button>,
      )}

      <Card as="div" className="filters">
        <div className="filter-row">
          <div role="group" aria-label="Work mode" className="chips">
            <FilterChip pressed={query.remote} onClick={() => setQuery({ ...query, remote: !query.remote })}>Remote</FilterChip>
            <FilterChip pressed={query.hybrid} onClick={() => setQuery({ ...query, hybrid: !query.hybrid })}>Hybrid</FilterChip>
          </div>
          <label className="field">
            Location
            <input
              type="text"
              placeholder="City or country"
              maxLength={120}
              value={query.location}
              onChange={(e) => setQuery({ ...query, location: e.target.value })}
              onKeyDown={(e) => e.key === "Enter" && !searching && search()}
            />
          </label>
          <label className="field">
            Salary range
            <select value={salary} onChange={(e) => setSalary(e.target.value)}>
              {SALARY.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </label>
        </div>
        <p className="muted">
          Work mode and location are used when searching{queryChanged ? " — search again to apply your changes" : ""}.
          Salary filters the list below. Sites searched: {state.sites.join(", ")}.
        </p>
      </Card>

      {error && <p className="error" role="alert">{error}</p>}
      {state.notice && <Notice>{state.notice}</Notice>}

      {searching ? (
        <Progress messages={SEARCH_MESSAGES} note="This takes about 30–60 seconds." interval={12000} />
      ) : state.status === "none" ? (
        <Card>
          <p>Choose a work mode and location, then click <strong>Find jobs</strong>. Postings come only from the sites listed
            above, and every match score is the share of a job's required skills you already have.</p>
        </Card>
      ) : (
        <div className="split">
          <Card className="split-main">
            {shown.length ? (
              <JobTable views={shown} selected={current?.job.id} onSelect={setSelected} caption="Jobs found, best match first" />
            ) : (
              <p>{state.jobs.length ? "No job matches this salary filter." : "No jobs in these results."}</p>
            )}
            <p className="muted">
              Match score is the share of a job's required skills you already have. It rises as you mark skills
              complete on <Link to="/progress">Progress Review</Link>.
            </p>
          </Card>
          {current && <JobDetail view={current} busy={busy} onMark={mark} />}
        </div>
      )}

      {state.kept.length > 0 && (
        <Card title="Saved and applied from earlier searches">
          <JobTable views={state.kept} selected={current?.job.id} onSelect={setSelected} caption="Saved and applied jobs" />
        </Card>
      )}
    </>
  );
}
