import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  downloadTailored, getOptimizer, getTailored, optimizeResume, resetTailoredEdits, saveTailoredEdits,
} from "../api.js";
import Button from "../components/Button.jsx";
import Card from "../components/Card.jsx";
import ConfirmDialog from "../components/ConfirmDialog.jsx";
import Icon from "../components/Icon.jsx";
import Notice from "../components/Notice.jsx";
import PageHeader from "../components/PageHeader.jsx";
import Progress from "../components/Progress.jsx";
import SkillBadge from "../components/SkillBadge.jsx";

const MESSAGES = [
  "Reading your resume and what you've completed…",
  "Matching your experience to the posting…",
  "Checking that nothing is invented…",
];

const plain = (segments) => segments.map((s) => s.text).join("");
const lines = (text) => text.split("\n").map((l) => l.trim()).filter(Boolean);

// A line whose added or reworded words are highlighted.
function Marked({ segments }) {
  return segments.map((s, i) => (s.added ? <mark key={i} className="added">{s.text}</mark> : <span key={i}>{s.text}</span>));
}

function Section({ title, children }) {
  return (
    <div className="resume-section">
      <h3 className="card-label">{title}</h3>
      {children}
    </div>
  );
}

function ResumeView({ doc, label }) {
  return (
    <Card className="resume-doc" aria-label={label}>
      <div className="card-label">{label}</div>
      <div>
        <div className="resume-name">{doc.name}</div>
        <div><Marked segments={doc.headline} /></div>
      </div>
      {doc.summary.length > 0 && <Section title="Summary"><p><Marked segments={doc.summary} /></p></Section>}
      {doc.roles.length > 0 && (
        <Section title="Experience">
          {doc.roles.map((r, i) => (
            <div key={i} className="stack-tight">
              <div className="resume-role">{r.title} · {r.employer} · <span className="muted">{r.dates}</span></div>
              {r.highlights.length > 0 && <ul>{r.highlights.map((h, j) => <li key={j}><Marked segments={h} /></li>)}</ul>}
            </div>
          ))}
        </Section>
      )}
      {doc.projects.length > 0 && (
        <Section title="Projects">
          {doc.projects.map((p, i) => (
            <div key={i} className="stack-tight">
              <div className="resume-role"><mark className="added">{p.title}</mark> <span className="muted">· dataset: {p.dataset}</span></div>
              <ul>{p.bullets.map((b, j) => <li key={j}><Marked segments={b} /></li>)}</ul>
            </div>
          ))}
        </Section>
      )}
      {doc.skills.length > 0 && (
        <Section title="Skills">
          <p>
            {doc.skills.map((s, i) => (
              <span key={s.name}>{s.added ? <mark className="added">{s.name}</mark> : s.name}{i < doc.skills.length - 1 ? ", " : ""}</span>
            ))}
          </p>
        </Section>
      )}
      {doc.achievements.length > 0 && <Section title="Achievements"><ul>{doc.achievements.map((a) => <li key={a}>{a}</li>)}</ul></Section>}
      {doc.courses.length > 0 && (
        <Section title="Courses and professional development">
          <ul>{doc.courses.map((c) => <li key={c.title}><mark className="added">{c.title}</mark>, {c.provider}</li>)}</ul>
        </Section>
      )}
      {doc.education.length > 0 && <Section title="Education"><ul>{doc.education.map((e) => <li key={e}>{e}</li>)}</ul></Section>}
      {doc.certifications.length > 0 && (
        <Section title="Certifications"><ul>{doc.certifications.map((c) => <li key={c}>{c}</li>)}</ul></Section>
      )}
    </Card>
  );
}

// Edit form: one textarea per block, one line per bullet. Employers, titles and dates are shown, not edited.
function EditForm({ doc, busy, onSave, onCancel }) {
  const [form, setForm] = useState({
    headline: plain(doc.headline),
    summary: plain(doc.summary),
    roles: doc.roles.map((r) => r.highlights.map(plain).join("\n")),
    projects: doc.projects.map((p) => p.bullets.map(plain).join("\n")),
    skills: doc.skills.map((s) => s.name).join(", "),
  });
  const set = (key, value) => setForm({ ...form, [key]: value });
  const setAt = (key, i, value) => set(key, form[key].map((v, j) => (j === i ? value : v)));

  function submit(e) {
    e.preventDefault();
    onSave({
      headline: form.headline.trim(),
      summary: form.summary.trim(),
      roles: form.roles.map(lines),
      projects: form.projects.map(lines),
      skills: form.skills.split(",").map((s) => s.trim()).filter(Boolean),
    });
  }

  return (
    <Card as="form" className="resume-doc" onSubmit={submit} aria-label="Edit the optimized resume">
      <div className="card-label">Edit the optimized resume</div>
      <p className="muted">One line per bullet. Fill in any [placeholders] with your own numbers. Employers, titles and
        dates come from your resume: change them by <Link to="/intake">reviewing your resume</Link>.</p>
      <label className="field">Headline
        <input type="text" maxLength={160} required value={form.headline} onChange={(e) => set("headline", e.target.value)} />
      </label>
      <label className="field">Summary
        <textarea rows={4} maxLength={800} required value={form.summary} onChange={(e) => set("summary", e.target.value)} />
      </label>
      {doc.roles.map((r, i) => (
        <label key={i} className="field">{r.title} · {r.employer} · {r.dates}
          <textarea rows={4} value={form.roles[i]} onChange={(e) => setAt("roles", i, e.target.value)} />
        </label>
      ))}
      {doc.projects.map((p, i) => (
        <label key={i} className="field">Project: {p.title}
          <textarea rows={3} value={form.projects[i]} onChange={(e) => setAt("projects", i, e.target.value)} />
        </label>
      ))}
      <label className="field">Skills (comma-separated)
        <textarea rows={2} value={form.skills} onChange={(e) => set("skills", e.target.value)} />
      </label>
      <div className="row">
        <Button type="submit" disabled={busy}>{busy ? "Saving…" : "Save changes"}</Button>
        <Button variant="secondary" onClick={onCancel} disabled={busy}>Cancel</Button>
      </div>
    </Card>
  );
}

function Suggestions({ view }) {
  return (
    <div className="card-row">
      <Card title="Added keywords">
        <p className="muted">From the posting, where your experience supports them.</p>
        {view.keywords.length ? (
          <div className="chips">{view.keywords.map((k) => <SkillBadge key={k} kind="skill">{k}</SkillBadge>)}</div>
        ) : <p className="muted">None this time.</p>}
      </Card>
      <Card title="To add once you have done this">
        <p className="muted">Not in your resume yet. Finish these on your roadmap, then optimize again.</p>
        {view.to_add.length ? (
          <ul className="rows">
            {view.to_add.map((a) => (
              <li key={`${a.kind}-${a.name}`}><strong>{a.name}</strong><span className="muted">{a.note}</span></li>
            ))}
          </ul>
        ) : <p className="muted">Nothing to add for this job.</p>}
      </Card>
      <Card title="Skill improvements">
        <p className="muted">What would lift this match from {view.job.score}%.</p>
        <ul className="rows">
          {view.improvements.map((m) => (
            <li key={m.skill} className="row row-between">
              <span>{m.skill}</span>
              <SkillBadge kind="gap">{m.phase ? `Phase ${m.phase}` : m.in_plan ? "In your plan" : "Missing"}</SkillBadge>
            </li>
          ))}
          {view.placeholders > 0 && (
            <li className="row row-between">
              <span>Fill in {view.placeholders} placeholder{view.placeholders > 1 ? "s" : ""} with your own numbers</span>
              <SkillBadge kind="plain">Your input</SkillBadge>
            </li>
          )}
        </ul>
        {!view.improvements.length && !view.placeholders && <p className="muted">You cover every required skill.</p>}
      </Card>
    </div>
  );
}

export default function ResumeOptimizer() {
  const [params, setParams] = useSearchParams();
  const [state, setState] = useState(null);
  const [view, setView] = useState(null);
  const [working, setWorking] = useState(false);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [copied, setCopied] = useState(false);

  const jobId = params.get("job") || state?.jobs[0]?.id || "";
  const option = state?.jobs.find((j) => j.id === jobId);

  useEffect(() => {
    let cancelled = false;
    getOptimizer().then((s) => !cancelled && setState(s)).catch((e) => !cancelled && setLoadError(e.message));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setView(null);
    setEditing(false);
    setError("");
    if (!option?.has_version) return undefined;
    getTailored(jobId).then((v) => !cancelled && setView(v)).catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [jobId, option?.has_version]);

  async function run(action) {
    setBusy(true);
    setError("");
    try {
      const next = await action();
      setView(next);
      return next;
    } catch (e) {
      setError(e.message);
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function optimize() {
    setConfirm(false);
    setWorking(true);
    setEditing(false);
    const next = await run(() => optimizeResume(jobId));
    setWorking(false);
    if (next) getOptimizer().then(setState).catch(() => {}); // the job list's "optimized" marks
  }

  async function save(edits) {
    if (await run(() => saveTailoredEdits(jobId, edits))) setEditing(false);
  }

  async function exportAs(format) {
    if (view.placeholders && !window.confirm("Some [placeholders] are still empty. Download anyway?")) return;
    setError("");
    const name = `resume-${view.job.job.company}-${view.job.job.title}`.toLowerCase().replace(/[^a-z0-9]+/g, "-");
    try {
      await downloadTailored(jobId, format, name);
    } catch (e) {
      setError(e.message);
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(view.text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("Copying isn't allowed in this browser. Download the DOCX instead.");
    }
  }

  const subtitle = option ? (
    <>Tailored for <Link to="/jobs">{option.title}</Link> at {option.company}</>
  ) : "Your resume, tailored to one job. Nothing is invented.";
  const header = (actions) => <PageHeader title="Resume Optimizer" subtitle={subtitle} actions={actions} />;

  if (loadError) return <>{header()}<Card><p className="error" role="alert">{loadError}</p></Card></>;
  if (!state) return <>{header()}<Card><p>Loading…</p></Card></>;
  if (!state.can_optimize) {
    return <>{header()}<Card><p>The optimizer works from your confirmed skills. Run your <Link to="/gaps">Skill Analysis</Link> first.</p></Card></>;
  }
  if (!state.jobs.length) {
    return <>{header()}<Card><p>Pick a job to tailor your resume to: <Link to="/jobs">find jobs on Job Match</Link> first.</p></Card></>;
  }

  const actions = view && !working && (
    <>
      <Button onClick={() => exportAs("pdf")}>Download PDF</Button>
      <Button variant="secondary" onClick={() => exportAs("docx")}>Download DOCX</Button>
      <Button variant="secondary" onClick={copy}>{copied ? "Copied ✓" : "Copy Content"}</Button>
    </>
  );

  return (
    <>
      {header(actions)}

      <Card as="div" className="filters">
        <div className="filter-row">
          <label className="field">
            Job
            <select value={jobId} onChange={(e) => setParams({ job: e.target.value })}>
              {state.jobs.map((j) => (
                <option key={j.id} value={j.id}>
                  {j.title} · {j.company} · {j.score}% match{j.has_version ? " · optimized" : ""}
                </option>
              ))}
            </select>
          </label>
          <Button
            onClick={() => (view?.edited ? setConfirm(true) : optimize())}
            disabled={working || busy || !jobId}
          >
            {working ? "Optimizing…" : view ? "Optimize again" : "Optimize my resume"}
          </Button>
        </div>
      </Card>

      <div className="notice-safe" role="note">
        <Icon name="shield" />
        <div><strong>Nothing here is invented.</strong> Every employer, title and date comes from your resume. Skills,
          projects and courses are added only once you have completed them on your roadmap.</div>
      </div>

      {error && <p className="error" role="alert">{error}</p>}
      {view?.stale && !working && (
        <Notice>Your progress or resume changed since this version was written. Optimize again to include it.</Notice>
      )}
      {view?.notice && !working && <Notice>{view.notice}</Notice>}
      {!state.has_resume && !view && (
        <Notice>You haven't uploaded a resume yet. <Link to="/intake">Upload one</Link> to include your work history.</Notice>
      )}

      {working ? (
        <Progress messages={MESSAGES} note="This takes about 15–30 seconds." interval={8000} />
      ) : !view ? (
        <Card>
          <p>Click <strong>Optimize my resume</strong> to tailor your resume to this job. It rewords and reorders what is
            already in your resume, and adds the skills, portfolio projects and courses you have completed.</p>
        </Card>
      ) : (
        <>
          <div className="split resume-compare">
            <ResumeView doc={view.original} label="Current resume" />
            {editing ? (
              <EditForm doc={view.tailored} busy={busy} onSave={save} onCancel={() => setEditing(false)} />
            ) : (
              <div className="resume-tailored">
                <ResumeView doc={view.tailored} label="Optimized resume" />
                <div className="row">
                  <span className="muted"><mark className="added">highlight</mark> = added or reworded</span>
                  <Button variant="secondary" onClick={() => setEditing(true)}>Edit</Button>
                  {view.edited && (
                    <Button variant="secondary" disabled={busy} onClick={() => run(() => resetTailoredEdits(jobId))}>
                      Undo my edits
                    </Button>
                  )}
                </div>
              </div>
            )}
          </div>
          <Suggestions view={view} />
        </>
      )}

      {confirm && (
        <ConfirmDialog
          title="Optimize again?"
          confirmLabel="Optimize again"
          busyLabel="Optimizing…"
          onCancel={() => setConfirm(false)}
          onConfirm={optimize}
        >
          <p>A new version replaces your edits to this one.</p>
        </ConfirmDialog>
      )}
    </>
  );
}
