import { useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import StepIndicator from "./components/StepIndicator.jsx";
import Intake from "./pages/Intake.jsx";
import Placeholder from "./pages/Placeholder.jsx";

export default function App() {
  const [userId, setUserId] = useState(() => {
    try {
      return localStorage.getItem("userId") || "";
    } catch {
      return "";
    }
  });
  const [draft, setDraft] = useState("");

  function signIn(e) {
    e.preventDefault();
    const id = draft.trim();
    if (!id) return;
    try {
      localStorage.setItem("userId", id);
    } catch {}
    setUserId(id);
  }

  function signOut() {
    try {
      localStorage.removeItem("userId");
    } catch {}
    setUserId("");
  }

  if (!userId) {
    return (
      <main className="card login">
        <h1>AI Career Strategist</h1>
        <p>Enter a user identifier. Use the same one next time to reload your saved profile.</p>
        <form onSubmit={signIn}>
          <input
            autoFocus
            value={draft}
            maxLength={64}
            placeholder="e.g. sindhu"
            onChange={(e) => setDraft(e.target.value)}
          />
          <button type="submit" disabled={!draft.trim()}>Start</button>
        </form>
      </main>
    );
  }

  return (
    <div className="shell">
      <header>
        <h1>AI Career Strategist</h1>
        <span className="user">
          {userId} · <button className="link" onClick={signOut}>switch user</button>
        </span>
      </header>
      <StepIndicator />
      <Routes>
        <Route path="/" element={<Navigate to="/intake" replace />} />
        <Route path="/intake" element={<Intake userId={userId} />} />
        <Route path="/gaps" element={<Placeholder title="Skill Gaps" />} />
        <Route path="/resources" element={<Placeholder title="Resources" />} />
        <Route path="/roadmap" element={<Placeholder title="Roadmap" />} />
      </Routes>
    </div>
  );
}
