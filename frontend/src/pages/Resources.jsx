import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { getResources, searchResources } from "../api.js";
import ResourceCard from "../components/ResourceCard.jsx";

export default function Resources() {
  const [state, setState] = useState(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const autoRan = useRef(false);

  async function run() {
    setRunning(true);
    setError("");
    try {
      setState(await searchResources());
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
        setState(s);
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

  const items = resources.gaps.flatMap((g) => g.resources);
  const totalHours = items.reduce((n, i) => n + i.resource.hours, 0);

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
      {error && <div className="card"><p className="error">{error}</p></div>}

      <section className="card">
        <h2>Learning resources for {profile.target_role}</h2>
        <p>
          {items.length} resources from our curated library, ranked for each skill gap by how well they match the skill,
          your AI experience ({profile.ai_experience}), your industry ({profile.domain}) and the time they take.
          Together about <strong>{totalHours} hours</strong> — your roadmap will schedule them around your{" "}
          {profile.hours_per_week} hrs/week.
        </p>
        <p className="muted">Live web search and refining this list by chat arrive in the next milestone.</p>
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
              {list.map((item) => <ResourceCard key={item.resource.id} item={item} profile={profile} />)}
            </ul>
          )}
        </section>
      ))}
    </main>
  );
}
