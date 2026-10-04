import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { analyzeGaps, confirmGaps, getGaps } from "../api.js";
import Progress from "../components/Progress.jsx";

const PRIORITY = { high: 0, medium: 1, low: 2 };

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

  if (loadError) return <main className="card"><p className="error">{loadError}</p></main>;
  if (!state) return <main className="card"><p>Loading…</p></main>;
  if (running) {
    return <Progress messages={progressMessages(state.profile)} note="This usually takes 20–40 seconds." />;
  }

  const { profile, analysis } = state;

  if (!profile.confirmed && (state.status === "none" || state.stale)) {
    return (
      <main className="card">
        <h2>Skill Gaps</h2>
        <p>
          {state.stale ? "Your profile changed since the last analysis. " : ""}
          Confirm your profile on the <Link to="/intake">Intake</Link> step first, then come back here.
        </p>
      </main>
    );
  }

  if (state.status === "none") {
    return (
      <main className="card">
        <h2>Skill Gaps</h2>
        {error && <p className="error">{error}</p>}
        <button onClick={() => run([])}>Analyze my skills</button>
      </main>
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

  // One gap row; `include` adds an "Add to my plan" correction for later / optional gaps.
  function gapItem(g, include) {
    const knows = { kind: "knows", skill: g.skill, text: `I already know ${g.skill}` };
    const want = { kind: "note", text: `Put "${g.skill}" in my plan now` };
    return (
      <li key={g.skill}>
        <div className="skill-head">
          <strong>{g.skill}</strong>
          <span className={`tag prio-${g.priority}`}>{g.priority}</span>
          <span className="tag">{g.effort_hours} h</span>
          {g.domain_specific && <span className="tag domain">{profile.domain}</span>}
        </div>
        <p className="muted">{g.why_needed}</p>
        <div className="row">
          <button className="link" disabled={noted.has(key(knows))} onClick={() => add(knows)}>
            {noted.has(key(knows)) ? "Noted" : "I already know this"}
          </button>
          {include && (
            <button className="link" disabled={noted.has(key(want))} onClick={() => add(want)}>
              {noted.has(key(want)) ? "Noted" : "Add to my plan"}
            </button>
          )}
        </div>
      </li>
    );
  }

  return (
    <main className="gaps">
      {state.stale && (
        <div className="card banner">
          Your profile changed since this analysis.{" "}
          <button className="link" onClick={() => run(pending)}>Re-run the analysis</button> to update it.
        </div>
      )}

      <section className="card">
        <h2>Your skill picture: {profile.current_role} → {profile.target_role}</h2>
        <p>{analysis.rationale}</p>
        <p className="muted">
          Skills marked <em>Assumed</em> are our best guess from your role, domain and AI experience. Correct anything
          that's wrong, then update the analysis.
        </p>
      </section>

      <div className="gap-grid">
        <section className="card">
          <h2>Strengths</h2>
          <ul className="skills">
            {analysis.strengths.map((s) => {
              const c = { kind: "lacks", skill: s.skill, text: `I don't have ${s.skill}` };
              return (
                <li key={s.skill}>
                  <div className="skill-head">
                    <strong>{s.skill}</strong>
                    <span className={`tag ${s.source}`}>{s.source === "user" ? "You said" : "Assumed"}</span>
                    <span className="tag">{s.category}</span>
                  </div>
                  <p className="muted">{s.basis}</p>
                  <button className="link" disabled={noted.has(key(c))} onClick={() => add(c)}>
                    {noted.has(key(c)) ? "Noted" : "I don't have this"}
                  </button>
                </li>
              );
            })}
          </ul>
        </section>

        <section className="card">
          <h2>Gaps to close</h2>
          <p className="muted">
            The {gaps.length} most important gaps for your 6-month plan: about <strong>{totalHours} hours</strong>,
            roughly {weeks} weeks at {profile.hours_per_week} hrs/week (your plan has {profile.hours_per_week * 26}{" "}
            hours).
          </p>
          <ul className="skills">{gaps.map((g) => gapItem(g, false))}</ul>
        </section>
      </div>

      {later.length > 0 && (
        <section className="card">
          <h2>Later / optional</h2>
          <p className="muted">
            Also useful for {profile.target_role}, but they don't fit this 6-month plan. No resources or roadmap time
            are planned for them. Add one to your plan and update the analysis to swap it in.
          </p>
          <ul className="skills">{later.map((g) => gapItem(g, true))}</ul>
        </section>
      )}

      <section className="card">
        <h2>AI use cases in {profile.domain}</h2>
        <div className="usecases">
          {analysis.domain_use_cases.map((u) => (
            <div key={u.title} className="usecase">
              <strong>{u.title}</strong>
              <p>{u.description}</p>
              <p className="muted">{u.relevance}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="card">
        <h2>Corrections</h2>
        <form className="row" onSubmit={addNote}>
          <input
            value={note}
            maxLength={300}
            placeholder={'Anything else we got wrong? e.g. "I\'ve never used Python"'}
            onChange={(e) => setNote(e.target.value)}
          />
          <button type="submit" className="secondary" disabled={!note.trim()}>Add</button>
        </form>
        {pending.length > 0 && (
          <ul className="chips">
            {pending.map((c) => (
              <li key={key(c)}>
                {c.text}
                <button className="link" aria-label="Remove" onClick={() => remove(key(c))}>×</button>
              </li>
            ))}
          </ul>
        )}
        {error && <p className="error">{error}</p>}
        <div className="row">
          <button className="secondary" onClick={() => run(pending)} disabled={!changed && !state.stale}>
            Update analysis
          </button>
          <button onClick={confirm} disabled={busy || changed || state.stale || state.confirmed}>
            {state.confirmed ? "Confirmed ✓" : "Confirm skills"}
          </button>
        </div>
        {changed && <p className="muted">Update the analysis to apply your corrections before confirming.</p>}
        {state.confirmed && (
          <p className="ok">Skills confirmed. See your <Link to="/resources">learning resources</Link>.</p>
        )}
      </section>
    </main>
  );
}
