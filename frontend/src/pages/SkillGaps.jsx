import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { analyzeGaps, confirmGaps, getGaps } from "../api.js";
import Button from "../components/Button.jsx";
import Card from "../components/Card.jsx";
import Notice from "../components/Notice.jsx";
import PageHeader from "../components/PageHeader.jsx";
import Progress from "../components/Progress.jsx";
import SkillBadge from "../components/SkillBadge.jsx";

const PRIORITY = { high: 0, medium: 1, low: 2 };
const PRIORITY_LABEL = { high: "High", medium: "Medium", low: "Low" };
const SUBTITLE = "What already transfers, and what to close first.";

function progressMessages({ target_role: role, domain }) {
  return [
    `Analyzing your skills for ${role} in ${domain}…`,
    `Working out what a ${role} needs day to day…`,
    `Finding the most relevant AI use cases in ${domain}…`,
    `Checking ${domain} data and compliance requirements…`,
    "Estimating the effort for each skill gap…",
    "Almost there — putting it all together…",
  ];
}

const key = (c) => `${c.kind}:${(c.skill || c.text).toLowerCase()}`;

export default function SkillGaps() {
  const [state, setState] = useState(null);
  const [pending, setPending] = useState([]); // corrections to send with the next run
  const [note, setNote] = useState("");
  const [running, setRunning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const autoRan = useRef(false);
  const navigate = useNavigate();

  async function run(corrections) {
    setRunning(true);
    setError("");
    try {
      const s = await analyzeGaps(corrections);
      setState(s);
      setPending(s.corrections);
    } catch (e) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    getGaps()
      .then((s) => {
        if (cancelled) return;
        setState(s);
        setPending(s.corrections);
        // First visit with a confirmed profile: start the analysis right away.
        if (s.status === "none" && s.profile.confirmed && !autoRan.current) {
          autoRan.current = true;
          run([]);
        }
      })
      .catch((e) => !cancelled && setLoadError(e.message));
    return () => {
      cancelled = true;
    };
  }, []);

  const plain = (children) => (
    <>
      <PageHeader title="Skill Analysis" subtitle={SUBTITLE} />
      {children}
    </>
  );

  if (loadError) return plain(<Card><p className="error" role="alert">{loadError}</p></Card>);
  if (!state) return plain(<Card><p>Loading…</p></Card>);
  if (running) {
    return plain(<Progress messages={progressMessages(state.profile)} note="This usually takes 20–40 seconds." />);
  }

  const { profile, analysis } = state;

  if (!profile.confirmed && (state.status === "none" || state.stale)) {
    return plain(
      <Card>
        <p>
          {state.stale ? "Your profile changed since the last analysis. " : ""}
          Confirm your profile on the <Link to="/intake">Intake</Link> step first, then come back here.
        </p>
      </Card>
    );
  }

  if (state.status === "none") {
    return plain(
      <Card>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="row"><Button onClick={() => run([])}>Analyze my skills</Button></div>
      </Card>
    );
  }

  const add = (c) => setPending((p) => (p.some((x) => key(x) === key(c)) ? p : [...p, c]));
  const remove = (k) => setPending((p) => p.filter((x) => key(x) !== k));
  const noted = new Set(pending.map(key));
  const changed = pending.map(key).join("|") !== state.corrections.map(key).join("|");

  function addNote(e) {
    e.preventDefault();
    const text = note.trim();
    if (!text) return;
    add({ kind: "note", text });
    setNote("");
  }

  async function confirm() {
    setBusy(true);
    setError("");
    try {
      setState(await confirmGaps());
      navigate("/resources");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const gaps = [...analysis.gaps].sort((a, b) => PRIORITY[a.priority] - PRIORITY[b.priority]);
  const totalHours = gaps.reduce((n, g) => n + g.effort_hours, 0);
  const weeks = Math.ceil(totalHours / profile.hours_per_week);
  const later = analysis.later_gaps || [];
  const lacks = (s) => ({ kind: "lacks", skill: s.skill, text: `I don't have ${s.skill}` });

  // Strengths of one source as badges; the × queues an "I don't have this" correction.
  function strengthGroup(source, caption) {
    const list = analysis.strengths.filter((s) => (s.source === "user") === (source === "user"));
    if (list.length === 0) return null;
    return (
      <div className="stack-tight">
        <div className="muted">{caption}</div>
        <div className="badges">
          {list.map((s) => (
            <SkillBadge
              key={s.skill}
              kind={source === "user" ? "skill" : "assumed"}
              noted={noted.has(key(lacks(s)))}
              onRemove={() => add(lacks(s))}
              removeLabel={`I don't have ${s.skill}`}
            >
              {s.skill}
            </SkillBadge>
          ))}
        </div>
      </div>
    );
  }

  // A table of gaps; `include` adds an "Add to my plan" correction for later / optional gaps.
  function gapTable(list, include) {
    return (
      <div className="table-scroll">
        <table className="table">
          <thead>
            <tr>
              <th scope="col">Skill</th>
              <th scope="col">Priority</th>
              <th scope="col">Effort</th>
              <th scope="col"><span className="sr-only">Corrections</span></th>
            </tr>
          </thead>
          <tbody>
            {list.map((g) => {
              const knows = { kind: "knows", skill: g.skill, text: `I already know ${g.skill}` };
              const want = { kind: "note", text: `Put "${g.skill}" in my plan now` };
              return (
                <tr key={g.skill}>
                  <th scope="row">
                    <strong>{g.skill}</strong>
                    {g.domain_specific && <> <span className="pill">{profile.domain}</span></>}
                    <p className="muted">{g.why_needed}</p>
                  </th>
                  <td className={`prio-${g.priority}`}>{PRIORITY_LABEL[g.priority]}</td>
                  <td className="num">{g.effort_hours} h</td>
                  <td>
                    <Button variant="text" disabled={noted.has(key(knows))} onClick={() => add(knows)}>
                      {noted.has(key(knows)) ? "Noted" : "I already know this"}
                    </Button>
                    {include && (
                      <Button variant="text" disabled={noted.has(key(want))} onClick={() => add(want)}>
                        {noted.has(key(want)) ? "Noted" : "Add to my plan"}
                      </Button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <>
      <PageHeader
        title="Skill Analysis"
        subtitle={`${profile.current_role} → ${profile.target_role}. ${SUBTITLE}`}
        actions={
          <>
            <Button variant="secondary" onClick={() => run(pending)} disabled={!changed && !state.stale}>
              Update analysis
            </Button>
            <Button onClick={confirm} disabled={busy || changed || state.stale || state.confirmed}>
              {state.confirmed ? "Confirmed ✓" : "Confirm skills"}
            </Button>
          </>
        }
      />

      {state.stale && (
        <Notice>
          Your profile changed since this analysis.{" "}
          <Button variant="text" onClick={() => run(pending)}>Re-run the analysis</Button> to update it.
        </Notice>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      {changed && <p className="muted">Update the analysis to apply your corrections before confirming.</p>}
      {state.confirmed && (
        <p className="ok">Skills confirmed. See your <Link to="/resources">learning resources</Link>.</p>
      )}

      <Card label="Summary" outlined>
        <p className="lead">{analysis.rationale}</p>
        <p className="muted">
          Skills marked <em>Assumed</em> are our best guess from your role, domain and AI experience. Correct anything
          that's wrong, then update the analysis.
        </p>
      </Card>

      <div className="card-row">
        <Card title="Existing skills">
          {strengthGroup("user", "You said")}
          {strengthGroup("assumed", "Assumed from your role. Remove any that are wrong.")}
          <details className="more">
            <summary>Why these skills</summary>
            <ul className="rows">
              {analysis.strengths.map((s) => (
                <li key={s.skill}>
                  <div className="row">
                    <strong>{s.skill}</strong>
                    <span className="pill">{s.source === "user" ? "You said" : "Assumed"}</span>
                    <span className="pill">{s.category}</span>
                  </div>
                  <p className="muted">{s.basis}</p>
                </li>
              ))}
            </ul>
          </details>
        </Card>

        <Card title="Missing skills">
          <div className="badges">
            {gaps.map((g) => <SkillBadge key={g.skill} kind="gap">{g.skill}</SkillBadge>)}
          </div>
          <form className="stack-tight divided" onSubmit={addNote}>
            <label htmlFor="correction" className="muted">Anything we got wrong?</label>
            <div className="chat-form">
              <input
                id="correction"
                value={note}
                maxLength={300}
                placeholder={'e.g. "I\'ve never used Python"'}
                onChange={(e) => setNote(e.target.value)}
              />
              <Button type="submit" variant="secondary" disabled={!note.trim()}>Add</Button>
            </div>
          </form>
          {pending.length > 0 && (
            <div className="stack-tight">
              <div className="muted">Your corrections</div>
              <div className="badges">
                {pending.map((c) => (
                  <SkillBadge key={key(c)} kind="plain" onRemove={() => remove(key(c))} removeLabel={`Remove correction: ${c.text}`}>
                    {c.text}
                  </SkillBadge>
                ))}
              </div>
            </div>
          )}
        </Card>
      </div>

      <Card>
        <div className="card-head">
          <h2>Skill gaps in your plan</h2>
          <span className="muted">
            {totalHours} of your {profile.hours_per_week * 26} hours · roughly {weeks} weeks at {profile.hours_per_week}{" "}
            hrs/week
          </span>
        </div>
        {gapTable(gaps, false)}
        {later.length > 0 && (
          <div className="stack-tight divided">
            <h3>Later / optional</h3>
            <p className="muted">
              Also useful for {profile.target_role}, but they don't fit this 6-month plan. No resources or roadmap time
              are planned for them. Add one to your plan and update the analysis to swap it in.
            </p>
            {gapTable(later, true)}
          </div>
        )}
      </Card>

      <section className="stack-tight">
        <h2>AI use cases in {profile.domain}</h2>
        <div className="card-row card-row-narrow">
          {analysis.domain_use_cases.map((u) => (
            <Card as="div" key={u.title} className="benefit">
              <strong>{u.title}</strong>
              <p>{u.description}</p>
              <p className="muted">{u.relevance}</p>
            </Card>
          ))}
        </div>
      </section>
    </>
  );
}
