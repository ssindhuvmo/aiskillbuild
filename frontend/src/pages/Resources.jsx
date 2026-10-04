import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { approveResources, getResources, searchResources } from "../api.js";
import ResourceCard from "../components/ResourceCard.jsx";

const WEEKS = 26; // roadmap length; the backend enforces the real budget (scheduler/budget.py)

const allItems = (s) => (s.resources ? s.resources.gaps.flatMap((g) => g.resources) : []);

// The saved approval if it still applies, otherwise everything selected.
function initialSelection(s) {
  const ids = allItems(s).map((i) => i.resource.id);
  return new Set(s.approved_ids && !s.approval_stale ? s.approved_ids : ids);
}

export default function Resources() {
  const [state, setState] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const [running, setRunning] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const autoRan = useRef(false);
  const navigate = useNavigate();

  function load(s) {
    setState(s);
    setSelected(initialSelection(s));
  }

  async function run() {
    setRunning(true);
    setError("");
    try {
      load(await searchResources());
    } catch (e) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    getResources()
      .then((s) => {
        if (cancelled) return;
        load(s);
        // First visit with confirmed skill gaps: build the list right away.
        if (s.status === "none" && s.gaps_confirmed && !autoRan.current) {
          autoRan.current = true;
          run();
        }
      })
      .catch((e) => !cancelled && setLoadError(e.message));
    return () => {
      cancelled = true;
    };
  }, []);

  if (loadError) return <main className="card"><p className="error">{loadError}</p></main>;
  if (!state) return <main className="card"><p>Loading…</p></main>;
  if (running) return <main className="card"><p>Finding resources for your skill gaps…</p></main>;

  const { profile, resources } = state;

  if (state.status === "none") {
    return (
      <main className="card">
        <h2>Resources</h2>
        {error && <p className="error">{error}</p>}
        {state.gaps_confirmed ? (
          <button onClick={run}>Find resources</button>
        ) : (
          <p>Confirm your skills on the <Link to="/gaps">Skill Gaps</Link> step first, then come back here.</p>
        )}
      </main>
    );
  }

  const items = allItems(state);
  const chosen = items.filter((i) => selected.has(i.resource.id));
  const hours = chosen.reduce((n, i) => n + i.resource.hours, 0);
  const budget = profile.hours_per_week * WEEKS;
  const saved = state.approved_ids && !state.approval_stale ? state.approved_ids : null;
  const approved = saved && saved.length === selected.size && saved.every((id) => selected.has(id));

  function toggle(id) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  }

  async function approve() {
    setBusy(true);
    setError("");
    try {
      load(await approveResources(chosen.map((i) => i.resource.id)));
      navigate("/roadmap");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="gaps">
      {state.stale && (
        <div className="card banner">
          {state.gaps_confirmed ? (
            <>
              Your skill gaps changed since this list was built.{" "}
              <button className="link" onClick={run}>Rebuild the list</button> to update it.
            </>
          ) : (
            <>
              Your profile or skill gaps changed. Confirm them on the <Link to="/gaps">Skill Gaps</Link> step, then
              rebuild this list.
            </>
          )}
        </div>
      )}

      <section className="card">
        <h2>Learning resources for {profile.target_role}</h2>
        <p>
          {items.length} resources from our curated library, ranked for each skill gap by how well they match the skill,
          your AI experience ({profile.ai_experience}), your industry ({profile.domain}) and the time they take.
          Untick anything you don't want, then approve the list to build your roadmap.
        </p>
        <p className="muted">Live web search and refining this list by chat arrive in a later milestone.</p>
      </section>

      {resources.gaps.map(({ gap, resources: list, note }) => (
        <section key={gap.skill} className="card">
          <div className="skill-head">
            <h2 className="inline">{gap.skill}</h2>
            <span className={`tag prio-${gap.priority}`}>{gap.priority}</span>
            <span className="tag">about {gap.effort_hours} h</span>
            {gap.domain_specific && <span className="tag domain">{profile.domain}</span>}
          </div>
          {note ? (
            <p className="muted">{note}</p>
          ) : (
            <ul className="skills resources">
              {list.map((item) => (
                <ResourceCard
                  key={item.resource.id}
                  item={item}
                  profile={profile}
                  selected={selected.has(item.resource.id)}
                  onToggle={toggle}
                />
              ))}
            </ul>
          )}
        </section>
      ))}

      <section className="card">
        <h2>Approve your list</h2>
        <p>
          <strong>{chosen.length} of {items.length}</strong> resources selected, about <strong>{hours} hours</strong>.
          Your roadmap has {budget} hours ({profile.hours_per_week} hrs/week × {WEEKS} weeks).
        </p>
        {hours > budget && (
          <p className="muted">
            That is more than fits. The roadmap will schedule the most important parts and list what it left out, or
            you can untick a few resources.
          </p>
        )}
        {error && <p className="error">{error}</p>}
        <div className="row">
          <button onClick={approve} disabled={busy || state.stale || chosen.length === 0 || approved}>
            {approved ? "Approved ✓" : "Approve list"}
          </button>
        </div>
        {approved && <p className="ok">List approved. See your <Link to="/roadmap">roadmap</Link>.</p>}
        {state.approval_stale && !state.stale && (
          <p className="muted">This list changed since you last approved it. Approve it again to update your roadmap.</p>
        )}
      </section>
    </main>
  );
}
