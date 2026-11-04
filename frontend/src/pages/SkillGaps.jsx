import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { adjustGap, analyzeGaps, confirmGaps, getGaps } from "../api.js";
import Button from "../components/Button.jsx";
import Card from "../components/Card.jsx";
import GapChart, { GapLegend } from "../components/GapChart.jsx";
import Notice from "../components/Notice.jsx";
import PageHeader from "../components/PageHeader.jsx";
import Progress from "../components/Progress.jsx";
import SkillBadge from "../components/SkillBadge.jsx";

const PRIORITY = { high: 0, medium: 1, low: 2 };
// Where each strength comes from, in the order the groups are shown.
const SOURCES = {
  resume: { label: "From your resume", caption: "From your resume", kind: "skill" },
  user: { label: "You said", caption: "You said", kind: "skill" },
  assumed: { label: "Assumed", caption: "Assumed from your role. Remove any that are wrong.", kind: "assumed" },
};
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
// Corrections shown as removable chips; the button corrections (not needed, later, plan) have their own controls.
const CHIP_KINDS = new Set(["knows", "lacks", "note"]);
const firstSentence = (text) => text.split(/(?<=[.!?])\s/)[0];
// One line on why an essential (high-priority) gap matters; the user's choice still stands.
const essential = (g, role) => `Core to ${role}: ${firstSentence(g.why_needed)}`;

export default function SkillGaps() {
  const [state, setState] = useState(null);
  const [pending, setPending] = useState([]); // corrections to send with the next run
  const [note, setNote] = useState("");
  const [running, setRunning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [adjusting, setAdjusting] = useState(false);
  const [removedNote, setRemovedNote] = useState(""); // after removing an essential gap
  const noticeRef = useRef(null);
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

  // Bring the budget suggestion or the essential-skill note into view when one appears.
  const suggestion = state?.suggestion;
  useEffect(() => {
    if (suggestion || removedNote) noticeRef.current?.scrollIntoView({ block: "nearest" });
  }, [suggestion, removedNote]);

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

  // A gap button: saved at once (no new analysis); queued notes stay queued.
  async function adjust(action, gap, makeRoom = []) {
    setAdjusting(true);
    setError("");
    setRemovedNote("");
    try {
      const s = await adjustGap(action, gap.skill, makeRoom);
      const queued = pending.filter((c) => !state.corrections.some((x) => key(x) === key(c)));
      setState(s);
      setPending([...s.corrections, ...queued.filter((c) => !s.corrections.some((x) => key(x) === key(c)))]);
      if (action === "not_needed" && gap.priority === "high") {
        setRemovedNote(`Removed "${gap.skill}". ${essential(gap, profile.target_role)} You can restore it below.`);
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setAdjusting(false);
    }
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
  const removed = state.corrections.filter((c) => c.kind === "not_needed" && c.gap);
  const lacks = (s) => ({ kind: "lacks", skill: s.skill, text: `I don't have ${s.skill}` });

  // Strengths of one source as badges; the × queues an "I don't have this" correction.
  function strengthGroup(source) {
    const list = analysis.strengths.filter((s) => s.source === source);
    if (list.length === 0) return null;
    return (
      <div key={source} className="stack-tight">
        <div className="muted">{SOURCES[source].caption}</div>
        <div className="badges">
          {list.map((s) => (
            <SkillBadge
              key={s.skill}
              kind={SOURCES[source].kind}
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

  // Buttons per gap. Plan: know it, move to later, not needed. Later / optional: add to plan, not needed.
  const gapButton = (action, label, g) => (
    <Button variant="text" disabled={adjusting} aria-label={`${label}: ${g.skill}`} onClick={() => adjust(action, g)}>
      {label}
    </Button>
  );
  const planActions = (g) => (
    <div className="gap-actions">
      {gapButton("knows", "I already know this", g)}
      {gapButton("later", "Move to later", g)}
      {gapButton("not_needed", "Not needed", g)}
    </div>
  );
  const laterActions = (g) => (
    <div className="gap-actions">
      {gapButton("plan", "Add to my plan", g)}
      {gapButton("not_needed", "Not needed", g)}
    </div>
  );

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
            <Button onClick={confirm} disabled={busy || adjusting || changed || state.stale || state.confirmed}>
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
          Strengths come from your resume, from what you told us, or are <em>assumed</em> from your role, industry and
          experience. Correct anything that's wrong, then update the analysis.
        </p>
      </Card>

      <div className="card-row">
        <Card title="Existing skills">
          {Object.keys(SOURCES).map(strengthGroup)}
          <details className="more">
            <summary>Why these skills</summary>
            <ul className="rows">
              {analysis.strengths.map((s) => (
                <li key={s.skill}>
                  <div className="row">
                    <strong>{s.skill}</strong>
                    <span className="pill">{SOURCES[s.source].label}</span>
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
          {pending.some((c) => CHIP_KINDS.has(c.kind)) && (
            <div className="stack-tight">
              <div className="muted">Your corrections</div>
              <div className="badges">
                {pending.filter((c) => CHIP_KINDS.has(c.kind)).map((c) => (
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
          <GapLegend>
            <span className="muted">
              {totalHours} of your {profile.hours_per_week * 26} hours · roughly {weeks} weeks at {profile.hours_per_week}{" "}
              hrs/week
            </span>
          </GapLegend>
        </div>
        <GapChart gaps={gaps} domain={profile.domain} actions={planActions} />
        <div ref={noticeRef}>
          {suggestion && (
            <Notice>
              {suggestion.message}{" "}
              {suggestion.fits && (
                <Button variant="text" disabled={adjusting} onClick={() => adjust("plan", suggestion, suggestion.move)}>
                  Move and add
                </Button>
              )}
              <Button variant="text" onClick={() => setState({ ...state, suggestion: null })}>
                {suggestion.fits ? "Cancel" : "OK"}
              </Button>
            </Notice>
          )}
          {removedNote && <Notice>{removedNote}</Notice>}
        </div>
        {later.length > 0 && (
          <div className="stack-tight divided">
            <h3>Later / optional</h3>
            <p className="muted">
              Also useful for {profile.target_role}, but they don't fit this 6-month plan. No resources or roadmap time
              are planned for them. Add one to your plan; if it doesn't fit your hours, we'll suggest what to move.
            </p>
            <GapChart gaps={later} domain={profile.domain} actions={laterActions} />
          </div>
        )}
        {removed.length > 0 && (
          <details className="more divided">
            <summary>Removed ({removed.length})</summary>
            <p className="muted">Marked not needed: left out of your plan, and a new analysis won't suggest them again.</p>
            <ul className="rows">
              {removed.map(({ gap: g }) => (
                <li key={g.skill}>
                  <div className="row">
                    <strong>{g.skill}</strong>
                    <Button variant="text" disabled={adjusting} aria-label={`Restore ${g.skill}`} onClick={() => adjust("restore", g)}>
                      Restore
                    </Button>
                  </div>
                  {g.priority === "high" && <p className="muted">{essential(g, profile.target_role)}</p>}
                </li>
              ))}
            </ul>
          </details>
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
