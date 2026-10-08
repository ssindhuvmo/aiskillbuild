import { useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import { Link, useNavigate } from "react-router-dom";
import { approveResources, getResources, removeResource, searchResources, streamChat } from "../api.js";
import Progress from "../components/Progress.jsx";
import ResourceCard from "../components/ResourceCard.jsx";

const WEEKS = 26; // roadmap length; the backend enforces the real budget (scheduler/budget.py)

const GREETING =
  "Here is your list. Tell me what to change — for example “I prefer free ones”, “add more hands-on projects” or “I already know PyTorch”. To drop a single resource, use its Remove button. When you're happy with the list, approve it.";

const PROGRESS = [
  "Searching our curated library…",
  "Searching the web for each skill gap…",
  "Checking that every link works…",
  "Ranking the results for you…",
];

const allItems = (s) => (s.resources ? s.resources.gaps.flatMap((g) => g.resources) : []);

export default function Resources() {
  const [state, setState] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [running, setRunning] = useState(false);
  const [sending, setSending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const autoRan = useRef(false);
  const bottom = useRef(null);
  const navigate = useNavigate();

  function load(s) {
    setState(s);
    setMessages(s.messages);
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

  useEffect(() => {
    // Scroll inside the chat log only, so the page doesn't jump away from the list.
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [messages]);

  if (loadError) return <main className="card"><p className="error">{loadError}</p></main>;
  if (!state) return <main className="card"><p>Loading…</p></main>;
  if (running) return <Progress messages={PROGRESS} note="This usually takes 30–90 seconds." interval={9000} />;

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
  const fromWeb = items.filter((i) => i.source === "web").length;
  const hours = items.reduce((n, i) => n + i.resource.hours, 0);
  const budget = profile.hours_per_week * WEEKS;
  const approved = state.approved_ids !== null && !state.approval_stale;

  async function send(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setError("");
    setSending(true);
    setMessages((m) => [...m, { role: "user", content: text }, { role: "assistant", content: "" }]);
    let failed = false;
    await streamChat("/api/resources/chat", text, {
      onToken: (t) =>
        setMessages((m) => {
          const copy = m.slice();
          const last = copy[copy.length - 1];
          copy[copy.length - 1] = { ...last, content: last.content + t };
          return copy;
        }),
      onState: (evt) => !failed && load(evt.resources), // the saved chat replaces the optimistic one
      onError: (msg) => {
        failed = true;
        setError(msg);
        setInput(text); // nothing was saved: let the user retry
        setMessages((m) => m.slice(0, -2));
      },
    });
    setSending(false);
  }

  // The quick path for a simple removal: no chat message and no AI call.
  async function remove(id) {
    setBusy(true);
    setError("");
    try {
      load(await removeResource(id));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    setBusy(true);
    setError("");
    try {
      load(await approveResources());
      navigate("/roadmap");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const shown = [{ role: "assistant", content: GREETING }, ...messages];

  return (
    <main className="gaps">
      {state.stale && (
        <div className="card banner">
          {state.gaps_confirmed ? (
            <>
              This list is out of date. <button className="link" onClick={run}>Rebuild the list</button> to update it
              and start refining.
            </>
          ) : (
            <>
              Your profile or skill gaps changed. Confirm them on the <Link to="/gaps">Skill Gaps</Link> step, then
              rebuild this list.
            </>
          )}
        </div>
      )}
      {state.notice && <div className="card banner">{state.notice}</div>}

      <section className="card">
        <h2>Learning resources for {profile.target_role}</h2>
        <p>
          {items.length} resources ({items.length - fromWeb} from our curated library, {fromWeb} found on the web),
          ranked for each skill gap by how well they match the skill, your AI experience ({profile.ai_experience}),
          your industry ({profile.domain}) and the time they take. Remove what you don't want, use the chat for
          anything else, then approve the list to build your roadmap.
        </p>
      </section>

      <div className="refine">
        <div className="gaps">
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
                      onRemove={remove}
                      disabled={busy || sending || state.stale}
                    />
                  ))}
                </ul>
              )}
            </section>
          ))}
        </div>

        <aside className="card chat refine-chat">
          <h2>Refine your list</h2>
          <div className="log">
            {shown.map((m, i) => (
              <div key={i} className={`msg ${m.role}`}>
                {m.role === "assistant" && m.content ? (
                  // react-markdown escapes raw HTML by default (no rehype-raw), so this stays safe.
                  <Markdown>{m.content}</Markdown>
                ) : (
                  m.content || (sending ? "Working on it…" : "")
                )}
              </div>
            ))}
            <div ref={bottom} />
          </div>
          {error && <p className="error">{error}</p>}
          <form onSubmit={send}>
            <input
              value={input}
              disabled={sending || state.stale}
              placeholder="What should change?"
              onChange={(e) => setInput(e.target.value)}
            />
            <button type="submit" disabled={sending || state.stale || !input.trim()}>{sending ? "…" : "Send"}</button>
          </form>

          <div className="approve">
            <p>
              <strong>{items.length} resources</strong>, about <strong>{hours} hours</strong>. Your roadmap has{" "}
              {budget} hours ({profile.hours_per_week} hrs/week × {WEEKS} weeks).
            </p>
            {hours > budget && (
              <p className="muted">
                That is more than fits. The roadmap will schedule the most important parts and list what it left out,
                or you can ask me to remove a few resources.
              </p>
            )}
            <button onClick={approve} disabled={busy || sending || state.stale || items.length === 0 || approved}>
              {approved ? "Approved ✓" : "Approve list"}
            </button>
            {approved && <p className="ok">List approved. See your <Link to="/roadmap">roadmap</Link>.</p>}
            {state.approval_stale && !state.stale && (
              <p className="muted">This list changed since you last approved it. Approve it again to update your roadmap.</p>
            )}
          </div>
        </aside>
      </div>
    </main>
  );
}
