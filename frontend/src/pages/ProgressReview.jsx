import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getProgressReview, recalcReadiness, refreshRoadmap, saveProgressReview } from "../api.js";
import Button from "../components/Button.jsx";
import Card from "../components/Card.jsx";
import ConfirmDialog from "../components/ConfirmDialog.jsx";
import MetricCard from "../components/MetricCard.jsx";
import Notice from "../components/Notice.jsx";
import PageHeader from "../components/PageHeader.jsx";
import SkillBadge from "../components/SkillBadge.jsx";

const COURSE_STATUS = { not_started: "Not started", started: "Started", completed: "Complete" };
const COURSE_KIND = { started: "skill", completed: "done" };
const MAX_NOTES = 2000;

// The editable part of the review: {skill: {completed, confidence}} and the notes.
function draftOf(review) {
  return {
    marks: Object.fromEntries(review.skills.map((s) => [s.skill, { completed: s.completed, confidence: s.confidence }])),
    notes: review.notes,
  };
}

function finished(course) {
  if (course.completed_at) return new Date(course.completed_at).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
  return course.status === "not_started" ? "Not yet" : "In progress";
}

export default function ProgressReview() {
  const [state, setState] = useState(null);
  const [draft, setDraft] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(null); // "save" | "recalc" | "refresh"
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [run, setRun] = useState(null); // refresh: { fromWeek, written, done, notices }

  function load(next) {
    setState(next);
    if (next.review) setDraft(draftOf(next.review));
    setDirty(false);
  }

  useEffect(() => {
    let cancelled = false;
    getProgressReview().then((s) => !cancelled && load(s)).catch((e) => !cancelled && setLoadError(e.message));
    return () => {
      cancelled = true;
    };
  }, []);

  function mark(skill, change) {
    setDraft((d) => ({ ...d, marks: { ...d.marks, [skill]: { ...d.marks[skill], ...change } } }));
    setDirty(true);
    setMessage("");
  }

  async function save() {
    const skills = Object.entries(draft.marks).map(([skill, m]) => ({ skill, ...m }));
    load(await saveProgressReview(skills, draft.notes));
  }

  async function act(kind, work) {
    setBusy(kind);
    setError("");
    setMessage("");
    try {
      await work();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  }

  const update = () => act("save", async () => {
    await save();
    setMessage("Progress saved. Your readiness score and dashboard are updated.");
  });

  const recalculate = () => act("recalc", async () => {
    if (dirty) await save();
    const { dashboard } = await recalcReadiness();
    setState((s) => ({ ...s, review: { ...s.review, readiness: dashboard.readiness } }));
    setMessage(`Readiness recalculated: ${dashboard.readiness}%. It is on your dashboard's progress trend.`);
  });

  // Saves unsaved marks first (completed skills drop out of the plan), then streams the replanned roadmap.
  const refresh = () => act("refresh", async () => {
    if (dirty) await save();
    setConfirming(false);
    let written = 0;
    let failed = false;
    setRun({ fromWeek: null, written: 0, done: false, notices: [] });
    await refreshRoadmap({
      onState: ({ from_week: fromWeek, phase, notice }) => {
        setRun((r) => ({
          ...r,
          fromWeek: fromWeek ?? r.fromWeek,
          written: phase ? ++written : r.written,
          notices: notice ? [...r.notices, notice] : r.notices,
        }));
      },
      onError: (msg) => {
        failed = true;
        setError(msg);
      },
    });
    setRun((r) => (failed ? null : { ...r, done: true }));
    load(await getProgressReview());
  });

  const header = (actions) => (
    <PageHeader title="Progress Review" subtitle="Tell us what you have finished. Your plan adjusts to it." actions={actions} />
  );

  if (loadError) return <>{header()}<Card><p className="error" role="alert">{loadError}</p></Card></>;
  if (!state) return <>{header()}<Card><p>Loading…</p></Card></>;
  if (state.status === "none") {
    return (
      <>
        {header()}
        <Card><p>Review your progress once you have a skill-gap analysis. Start on the <Link to="/gaps">Skill Analysis</Link> step.</p></Card>
      </>
    );
  }

  const r = state.review;
  const working = busy !== null;

  return (
    <>
      {header(
        <>
          <Button onClick={update} disabled={working || !dirty}>{busy === "save" ? "Saving…" : "Update Progress"}</Button>
          <Button variant="secondary" onClick={recalculate} disabled={working}>
            {busy === "recalc" ? "Recalculating…" : "Recalculate Readiness Score"}
          </Button>
        </>,
      )}

      {error && <p className="error" role="alert">{error}</p>}
      {message && <Notice>{message}</Notice>}
      {dirty && !working && <p className="muted" role="status">You have unsaved changes.</p>}

      <Card className="refresh-banner">
        <div className="stack-tight">
          <h2>
            {r.behind_hours > 0
              ? `You are ${r.behind_hours} hour${r.behind_hours === 1 ? "" : "s"} behind your plan`
              : "You are on track with your plan"}
          </h2>
          {r.can_refresh ? (
            <p className="muted">
              Refreshing keeps everything you have completed and replans only weeks {r.from_week} to 26. Skills you mark
              complete and resources you finished drop out of the plan.
            </p>
          ) : (
            <p className="muted">
              {r.refresh_reason} <Link to="/roadmap">Open the roadmap</Link>
            </p>
          )}
        </div>
        <div className="refresh-side">
          <MetricCard label="Readiness" value={`${r.readiness}%`} />
          <Button onClick={() => setConfirming(true)} disabled={working || !r.can_refresh}>
            {busy === "refresh" ? "Refreshing…" : "Refresh my plan"}
          </Button>
        </div>
      </Card>

      {run && (
        <Notice>
          {run.done ? (
            <>
              Your plan is refreshed from week {run.fromWeek}. <Link to="/roadmap">See the updated roadmap</Link>.
            </>
          ) : (
            <>
              Replanning{run.fromWeek ? ` weeks ${run.fromWeek} to 26` : ""}… writing the text of the phases that are
              not over ({run.written} done).
            </>
          )}
        </Notice>
      )}
      {run?.notices.map((n) => <Notice key={n}>{n}</Notice>)}

      <div className="card-row">
        <Card title="Completed skills">
          <p className="muted">Tick a skill when you can do it at the level the role needs.</p>
          <div className="check-list">
            {r.skills.map((s) => (
              <label key={s.skill} className="check-row">
                <input
                  type="checkbox"
                  checked={draft.marks[s.skill].completed}
                  disabled={working}
                  onChange={(e) => mark(s.skill, { completed: e.target.checked })}
                />
                <span>{s.skill}</span>
                <span className="muted">{s.current_level} → {s.target_level}</span>
              </label>
            ))}
          </div>
        </Card>

        <Card title="Confidence rating">
          <p className="muted">How confident are you in each skill today? 1 is not at all, 5 is ready for the job.</p>
          <div className="stack">
            {r.skills.map((s, i) => {
              const value = draft.marks[s.skill].confidence;
              const id = `confidence-${i}`;
              return (
                <div key={s.skill} className="stack-tight">
                  <div className="row row-between">
                    <label htmlFor={id}>{s.skill}</label>
                    <span className="muted">{value ? `${value} of 5` : "Not rated"}</span>
                  </div>
                  <input
                    id={id}
                    type="range"
                    min="1"
                    max="5"
                    step="1"
                    value={value ?? 1}
                    disabled={working}
                    aria-valuetext={value ? `${value} of 5` : "Not rated"}
                    onChange={(e) => mark(s.skill, { confidence: Number(e.target.value) })}
                  />
                </div>
              );
            })}
          </div>
        </Card>
      </div>

      <Card>
        <div className="row row-between">
          <h2>Courses finished</h2>
          <span className="muted">Self-reported. We take your word for it.</span>
        </div>
        {r.courses.length ? (
          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Resource</th>
                  <th scope="col">Skill</th>
                  <th scope="col">Hours</th>
                  <th scope="col">Finished</th>
                  <th scope="col">Status</th>
                </tr>
              </thead>
              <tbody>
                {r.courses.map((c) => (
                  <tr key={c.resource_id}>
                    <th scope="row"><a href={c.url} target="_blank" rel="noopener noreferrer">{c.title} ↗</a></th>
                    <td>{c.skill}</td>
                    <td className="num">{c.status === "completed" ? `${c.hours} h` : `${c.hours_done} of ${c.hours} h`}</td>
                    <td>{finished(c)}</td>
                    <td><SkillBadge kind={COURSE_KIND[c.status] || "plain"}>{COURSE_STATUS[c.status]}</SkillBadge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p>Approve your <Link to="/resources">resource list</Link> to track courses here.</p>
        )}
        <p className="muted">
          Mark a resource Complete on the <Link to="/resources">Resources</Link> page, or tick its tasks on the{" "}
          <Link to="/roadmap">roadmap</Link>.
        </p>
      </Card>

      <Card>
        <label className="field">
          Notes
          <textarea
            rows={4}
            maxLength={MAX_NOTES}
            value={draft.notes}
            disabled={working}
            placeholder="What went well, what was hard, anything that changed (new project at work, less time next month)…"
            onChange={(e) => {
              setDraft((d) => ({ ...d, notes: e.target.value }));
              setDirty(true);
              setMessage("");
            }}
          />
        </label>
      </Card>

      {confirming && (
        <ConfirmDialog
          title="Refresh your plan?"
          confirmLabel="Refresh my plan"
          busyLabel="Refreshing…"
          busy={busy === "refresh"}
          onCancel={() => setConfirming(false)}
          onConfirm={refresh}
        >
          <p>
            Everything you have checked off stays where it is. Unfinished work moves to week {r.from_week} and later,
            and the text of the phases that are not over is written again.
            {dirty && " Your unsaved changes are saved first."}
          </p>
        </ConfirmDialog>
      )}
    </>
  );
}
