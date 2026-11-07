import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  approveResources, filterResources, getResources, removeResource, searchResources, setResourceProgress, streamChat,
} from "../api.js";
import Button from "../components/Button.jsx";
import Card from "../components/Card.jsx";
import Chat from "../components/Chat.jsx";
import ConfirmDialog from "../components/ConfirmDialog.jsx";
import Notice from "../components/Notice.jsx";
import PageHeader from "../components/PageHeader.jsx";
import Progress from "../components/Progress.jsx";
import ResourceCard, { ProgressButtons } from "../components/ResourceCard.jsx";
import ResourceFilters from "../components/ResourceFilters.jsx";

const WEEKS = 26; // roadmap length; the backend enforces the real budget (scheduler/budget.py)
const PRIORITY_LABEL = { high: "High priority", medium: "Medium priority", low: "Low priority" };
const SUBTITLE = "Picked for your gaps, your budget and how you like to learn.";

const GREETING =
  "Here is your list. Tell me what to change — for example “I prefer free ones”, “add more hands-on projects” or “I already know PyTorch”. To drop a single resource, use its Remove button; the filters above the list narrow it down. When you're happy with the list, approve it.";

const PROGRESS = [
  "Searching our curated library…",
  "Searching the web for each skill gap…",
  "Searching YouTube for full courses…",
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
  const [error, setError] = useState(""); // from the buttons
  const [chatError, setChatError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [confirmRebuild, setConfirmRebuild] = useState(false);
  const autoRan = useRef(false);
  const navigate = useNavigate();

  function load(s) {
    setState(s);
    setMessages(s.messages);
  }

  async function run() {
    setRunning(true);
    setError("");
    setChatError("");
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

  const plain = (children) => (
    <>
      <PageHeader title="Resources" subtitle={SUBTITLE} />
      {children}
    </>
  );

  if (loadError) return plain(<Card><p className="error" role="alert">{loadError}</p></Card>);
  if (!state) return plain(<Card><p>Loading…</p></Card>);
  if (running) return plain(<Progress messages={PROGRESS} note="This usually takes 30–90 seconds." interval={9000} />);

  const { profile, resources } = state;

  if (state.status === "none") {
    return plain(
      <Card>
        {error && <p className="error" role="alert">{error}</p>}
        {state.gaps_confirmed ? (
          <div className="row"><Button onClick={run}>Find resources</Button></div>
        ) : (
          <p>Confirm your skills on the <Link to="/gaps">Skill Analysis</Link> step first, then come back here.</p>
        )}
      </Card>
    );
  }

  const items = allItems(state);
  const count = (source) => items.filter((i) => i.source === source).length;
  const progressById = Object.fromEntries(state.progress.map((p) => [p.resource.id, p]));
  const offList = state.progress.filter((p) => !items.some((i) => i.resource.id === p.resource.id));
  const hours = items.reduce((n, i) => n + i.resource.hours, 0);
  const budget = profile.hours_per_week * WEEKS;
  const approved = state.approved_ids !== null && !state.approval_stale;

  async function send(text) {
    if (sending) return;
    setInput("");
    setChatError("");
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
        setChatError(msg);
        setInput(text); // nothing was saved: let the user retry
        setMessages((m) => m.slice(0, -2));
      },
    });
    setSending(false);
  }

  // Filter chips change the list itself (no chat message, no AI call, no new search).
  async function applyFilters(filters) {
    setBusy(true);
    setError("");
    try {
      load(await filterResources(filters));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  // Save / Start / Complete: recorded on its own, never changes the list.
  async function markProgress(id, change) {
    setError("");
    try {
      setState(await setResourceProgress(id, change));
    } catch (e) {
      setError(e.message);
    }
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
    <>
      <PageHeader
        title="Resources"
        subtitle={SUBTITLE}
        actions={
          <>
            <span className="header-stat">{items.length} resources · {hours} h of your {budget} h</span>
            <Button variant="secondary" onClick={() => setConfirmRebuild(true)}
              disabled={busy || sending || !state.gaps_confirmed}>
              Search again
            </Button>
            <Button onClick={approve} disabled={busy || sending || state.stale || items.length === 0 || approved}>
              {approved ? "Approved ✓" : "Approve list"}
            </Button>
          </>
        }
      />

      {confirmRebuild && (
        <ConfirmDialog
          title="Search again?"
          confirmLabel="Search again"
          busyLabel="Searching…"
          onCancel={() => setConfirmRebuild(false)}
          onConfirm={() => {
            setConfirmRebuild(false);
            run();
          }}
        >
          <p>
            This builds a new list from the curated library, the web and YouTube. It replaces the current list, your
            filters and the refinement chat; if you approved the list, approve the new one to update your roadmap.
            Saved, started and completed resources are kept.
          </p>
        </ConfirmDialog>
      )}

      {state.stale && (
        <Notice>
          {state.gaps_confirmed ? (
            <>
              This list is out of date. <Button variant="text" onClick={run}>Rebuild the list</Button> to update it
              and start refining.
            </>
          ) : (
            <>
              Your profile or skill gaps changed. Confirm them on the <Link to="/gaps">Skill Analysis</Link> step, then
              rebuild this list.
            </>
          )}
        </Notice>
      )}
      {state.notice && <Notice>{state.notice}</Notice>}
      {error && <p className="error" role="alert">{error}</p>}
      {approved && <p className="ok">List approved. See your <Link to="/roadmap">roadmap</Link>.</p>}
      {state.approval_stale && !state.stale && (
        <p className="muted">This list changed since you last approved it. Approve it again to update your roadmap.</p>
      )}

      <Card title="Filters">
        <ResourceFilters
          preferences={state.preferences}
          freeOnly={state.free_only}
          disabled={busy || sending || state.stale}
          onChange={applyFilters}
        />
      </Card>

      <p className="muted">
        {count("knowledge_base")} from our curated library, {count("web")} found on the web, {count("youtube")} from
        YouTube, ranked for each skill gap by how well they match the skill, your AI level ({profile.ai_level}), your
        industry ({profile.domain}), how you like to learn, the time they take and, for YouTube, views and likes. Your roadmap has {budget} hours ({profile.hours_per_week} hrs/week × {WEEKS} weeks).
        {hours > budget &&
          " This list is more than fits: the roadmap will schedule the most important parts and list what it left out, or you can ask to remove a few resources."}
      </p>

      <div className="split">
        <div className="split-main stack">
          {resources.gaps.map(({ gap, resources: list, note }) => (
            <section key={gap.skill} className="stack-tight">
              <div className="gap-head">
                <h2>{gap.skill}</h2>
                <span className={`prio-${gap.priority}`}>{PRIORITY_LABEL[gap.priority]}</span>
                <span className="muted">about {gap.effort_hours} h to close</span>
                {gap.domain_specific && <span className="pill">{profile.domain}</span>}
              </div>
              {note ? (
                <p className="muted">{note}</p>
              ) : (
                list.map((item) => (
                  <ResourceCard
                    key={item.resource.id}
                    item={item}
                    profile={profile}
                    progress={progressById[item.resource.id]}
                    onProgress={(change) => markProgress(item.resource.id, change)}
                    onRemove={remove}
                    disabled={busy || sending || state.stale}
                  />
                ))
              )}
            </section>
          ))}

          {offList.length > 0 && (
            <Card title="Saved and in progress, not on this list">
              <ul className="rows">
                {offList.map((p) => (
                  <li key={p.resource.id}>
                    <a href={p.resource.url} target="_blank" rel="noopener noreferrer">{p.resource.title} ↗</a>
                    <span className="muted">{p.resource.provider} · {p.resource.hours} h</span>
                    <ProgressButtons
                      title={p.resource.title}
                      saved={p.saved}
                      status={p.status}
                      onProgress={(change) => markProgress(p.resource.id, change)}
                    />
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>

        <Card as="aside" title="Refine your list" aria-label="Refine your list" className="split-side sticky chat-compact">
          <Chat
            messages={shown}
            sending={sending}
            waitingText="Working on it…"
            value={input}
            onChange={setInput}
            onSend={send}
            disabled={state.stale}
            label="Ask for a change"
            placeholder="Ask for a change…"
            error={chatError}
          />
        </Card>
      </div>
    </>
  );
}
