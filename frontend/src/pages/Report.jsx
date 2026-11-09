import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { downloadReport, generateReport, getReport } from "../api.js";
import Button from "../components/Button.jsx";
import Card from "../components/Card.jsx";
import Notice from "../components/Notice.jsx";
import PageHeader from "../components/PageHeader.jsx";
import Progress from "../components/Progress.jsx";
import SkillBadge from "../components/SkillBadge.jsx";
import { PRIORITY_KIND, STATUS, STATUS_KIND, formatDay } from "../tracking.js";

// The AI Career Transition Report (SPEC.md section 8). Only the Career Fit Assessment and the Recommended
// Career Strategy are written by the AI; the backend assembles every other section from saved data.

const MESSAGES = ["Reading your profile, skills and roadmap…", "Writing your career fit assessment…", "Writing your career strategy…"];
const SOURCE = { resume: "From resume", user: "From you", assumed: "Assumed" };
const SOURCE_KIND = { resume: "skill", user: "skill", assumed: "assumed" };
const capitalize = (s) => s[0].toUpperCase() + s.slice(1);

function Paragraphs({ text }) {
  return text.split(/\n\s*\n/).filter((p) => p.trim()).map((p, i) => <p key={i}>{p.trim()}</p>);
}

function Section({ n, title, children }) {
  return (
    <Card title={`${n}. ${title}`} className="report-section">
      {children}
    </Card>
  );
}

function GapItem({ gap }) {
  return (
    <li className="stack-tight">
      <div className="row">
        <strong>{gap.skill}</strong>
        <SkillBadge kind={PRIORITY_KIND[gap.priority]}>{capitalize(gap.priority)} priority</SkillBadge>
        <span className="muted">{gap.current_level} → {gap.target_level}</span>
      </div>
      <span>{gap.why_needed}</span>
    </li>
  );
}

function profileRows(p) {
  const rows = [];
  if (p.years_experience != null) rows.push(["Experience", `${p.years_experience} years`]);
  if (p.ai_level) rows.push(["Overall AI level", p.ai_level]);
  for (const [area, level] of Object.entries(p.capabilities)) rows.push([area, level]);
  if (p.learning_preferences.length) rows.push(["Learning preferences", p.learning_preferences.join(", ")]);
  if (p.constraints.length) rows.push(["Constraints", p.constraints.join("; ")]);
  if (p.additional_context) rows.push(["Context", p.additional_context]);
  if (p.resume) {
    if (p.resume.roles.length) rows.push(["Roles", p.resume.roles.join("; ")]);
    if (p.resume.certifications.length) rows.push(["Certifications", p.resume.certifications.join("; ")]);
    if (p.resume.education.length) rows.push(["Education", p.resume.education.join("; ")]);
    if (p.resume.skills.length) rows.push(["Resume skills", p.resume.skills.join(", ")]);
  }
  return rows;
}

function ReportBody({ report: r }) {
  const g = r.career_goal;
  return (
    <>
      <Section n={1} title="Career Goal">
        <p>
          Move from <strong>{g.current_role}</strong> to <strong>{g.target_role}</strong> in {g.domain}, over {g.weeks} weeks
          at up to {g.hours_per_week} hours a week, starting {formatDay(r.start_date, true)}.
        </p>
      </Section>

      <Section n={2} title="Current Career Profile">
        <dl className="fields report-fields">
          {profileRows(r.current_profile).map(([k, v]) => (
            <div key={k}>
              <dt>{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      </Section>

      <Section n={3} title="Career Fit Assessment">
        <Paragraphs text={r.career_fit} />
      </Section>

      <Section n={4} title="Transferable Skills">
        <ul className="report-list">
          {r.transferable_skills.map((s) => (
            <li key={s.skill} className="stack-tight">
              <div className="row">
                <strong>{s.skill}</strong>
                <SkillBadge kind={SOURCE_KIND[s.source]}>{SOURCE[s.source]}</SkillBadge>
              </div>
              <span>{s.basis}</span>
            </li>
          ))}
        </ul>
      </Section>

      <Section n={5} title="Capability Gap Analysis">
        <ul className="report-list">
          {r.gaps.map((gap) => <GapItem key={gap.skill} gap={gap} />)}
        </ul>
        {r.later_gaps.length > 0 && (
          <>
            <h3>Later / optional</h3>
            <ul className="report-list">
              {r.later_gaps.map((gap) => <GapItem key={gap.skill} gap={gap} />)}
            </ul>
          </>
        )}
      </Section>

      <Section n={6} title="Recommended Career Strategy">
        <Paragraphs text={r.strategy} />
      </Section>

      <Section n={7} title="Prioritized Learning Plan">
        <ol className="report-list numbered">
          {r.learning_plan.map((i) => (
            <li key={i.skill}>
              <strong>{i.skill}</strong>{" "}
              <span className="muted">
                · {i.priority} priority · {i.current_level} → {i.target_level} ·{" "}
                {i.phase ? `phase ${i.phase}` : "not scheduled"} · {i.resource_hours} h of resources
              </span>
            </li>
          ))}
        </ol>
      </Section>

      <Section n={8} title="Recommended Learning Resources">
        <ul className="report-list">
          {r.resources.map((x) => (
            <li key={x.url}>
              <a href={x.url} target="_blank" rel="noopener noreferrer">{x.title} ↗</a>{" "}
              <span className="muted">
                {x.provider} · {x.format} · {x.cost} · {x.hours} h · for {x.gap}
                {!x.scheduled && " · not scheduled"}
              </span>
            </li>
          ))}
        </ul>
      </Section>

      <Section n={9} title="Six-Month Career Transition Roadmap">
        <p className="muted">
          {r.planned_hours} of {r.budget_hours} budgeted hours planned, starting {formatDay(r.start_date, true)}.{" "}
          <Link to="/roadmap">Open the full roadmap</Link>
        </p>
        {r.roadmap.map((ph) => (
          <div key={ph.number} className="stack-tight report-phase">
            <div className="row">
              <h3>Phase {ph.number}: {ph.name}</h3>
              {ph.status !== "not_started" && <SkillBadge kind={STATUS_KIND[ph.status] || "plain"}>{STATUS[ph.status]}</SkillBadge>}
            </div>
            <span className="muted">
              Months {ph.months.join("–")} · {ph.hours} h{ph.gaps.length > 0 && ` · ${ph.gaps.join(", ")}`}
            </span>
            <ul className="report-list">
              {ph.milestones.map((m) => (
                <li key={m.month}>
                  <strong>Month {m.month}, {m.theme}</strong>{" "}
                  <span className={m.done ? "done-text" : "muted"}>· {m.done ? "Done" : `due ${formatDay(m.due)}`}</span>
                  <br />
                  {m.milestone}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </Section>

      <Section n={10} title="Recommended Portfolio Projects">
        {r.projects.map((p) => (
          <div key={p.phase} className="stack-tight report-phase">
            <div className="card-label">Phase {p.phase} · {g.domain}</div>
            <h3>{p.title}</h3>
            <p>{p.problem}</p>
            <p className="muted">Dataset: {p.dataset}</p>
            <ul className="plain-list">
              {p.deliverables.map((d) => <li key={d}>{d}</li>)}
            </ul>
          </div>
        ))}
      </Section>

      <Section n={11} title="Immediate Next Steps">
        {r.next_steps.length ? (
          <ol className="next-steps">
            {r.next_steps.map((s) => (
              <li key={s.task_id}>
                <span>{s.title}</span>
                <span className={s.overdue ? "next-step-meta overdue" : "next-step-meta"}>
                  {s.hours} h · {s.overdue ? `overdue since ${formatDay(s.due)}` : `week ${s.week}, due ${formatDay(s.due)}`}
                </span>
              </li>
            ))}
          </ol>
        ) : (
          <p>Every task in your roadmap is done.</p>
        )}
      </Section>
    </>
  );
}

export default function Report() {
  const [state, setState] = useState(null);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let cancelled = false;
    getReport()
      .then((s) => !cancelled && setState(s))
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, []);

  async function create() {
    setWorking(true);
    setError("");
    setNotice("");
    try {
      const next = await generateReport();
      setState(next);
      setNotice(next.notice || "");
    } catch (e) {
      setError(e.message);
    } finally {
      setWorking(false);
    }
  }

  const download = (format) => downloadReport(format).catch((e) => setError(e.message));
  const ready = state?.status === "ready";
  const header = (
    <PageHeader
      title="Transition Report"
      subtitle="Your AI career transition in one document: where you stand, what to learn and what to do next."
      actions={
        ready && !working && (
          <>
            <Button onClick={() => download("pdf")}>Download PDF</Button>
            <Button variant="secondary" onClick={() => download("md")}>Download Markdown</Button>
            <Button variant="secondary" onClick={create} disabled={!state.can_generate}>Regenerate</Button>
          </>
        )
      }
    />
  );

  if (!state) {
    return (
      <>
        {header}
        <Card>{error ? <p className="error" role="alert">{error}</p> : <p>Loading…</p>}</Card>
      </>
    );
  }
  if (working) {
    return (
      <>
        {header}
        <Progress messages={MESSAGES} note="This takes about 10–20 seconds." interval={5000} />
      </>
    );
  }

  return (
    <>
      {header}
      {error && <p className="error" role="alert">{error}</p>}
      {notice && <Notice>{notice}</Notice>}
      {!ready && (
        <Card>
          {state.can_generate ? (
            <>
              <p>
                The report brings together your profile, skill analysis, approved resources and roadmap. The AI writes
                your career fit assessment and strategy; everything else comes from what you have already saved.
              </p>
              <div className="row"><Button onClick={create}>Create my report</Button></div>
            </>
          ) : (
            <p>Build your <Link to="/roadmap">Learning Roadmap</Link> from your approved resources first, then come back here.</p>
          )}
        </Card>
      )}
      {ready && state.stale && (
        <Notice>
          {state.can_generate ? (
            <>
              Your profile, skills, resources or roadmap changed since this report was written.{" "}
              <Button variant="text" onClick={create}>Regenerate the report</Button> to update the assessment and strategy.
            </>
          ) : (
            <>
              Your profile, skills or resources changed. Rebuild your <Link to="/roadmap">roadmap</Link>, then
              regenerate this report.
            </>
          )}
        </Notice>
      )}
      {ready && state.report.narrative_source === "default" && !notice && (
        <Notice>The assessment and strategy show plain text because the AI's text wasn't available. Regenerate to try again.</Notice>
      )}
      {ready && <ReportBody report={state.report} />}
    </>
  );
}
