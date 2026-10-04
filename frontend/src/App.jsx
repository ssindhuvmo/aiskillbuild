import { useCallback, useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { getMe, googleLogin, logout, setUnauthorizedHandler, startOver } from "./api.js";
import GoogleSignIn, { loadGis } from "./components/GoogleSignIn.jsx";
import StepIndicator from "./components/StepIndicator.jsx";
import Intake from "./pages/Intake.jsx";
import Resources from "./pages/Resources.jsx";
import Roadmap from "./pages/Roadmap.jsx";
import SkillGaps from "./pages/SkillGaps.jsx";

export default function App() {
  const [user, setUser] = useState(undefined); // undefined = checking session, null = signed out
  const [error, setError] = useState("");
  const [confirmReset, setConfirmReset] = useState(false);
  const [resetting, setResetting] = useState(false);

  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null));
    getMe()
      .then(setUser)
      .catch((e) => {
        setUser(null);
        if (e.status !== 401) setError(e.message);
      });
  }, []);

  const signIn = useCallback(async (credential) => {
    setError("");
    try {
      setUser(await googleLogin(credential));
    } catch (e) {
      setError(e.message);
    }
  }, []);

  async function signOut() {
    try {
      await logout();
    } catch {}
    // Stop Google One Tap from silently signing the same account back in.
    loadGis().then((g) => g.accounts.id.disableAutoSelect()).catch(() => {});
    setUser(null);
  }

  async function reset() {
    setResetting(true);
    setError("");
    try {
      await startOver();
      // Full reload so every page drops its loaded state and starts from an empty profile.
      window.location.assign("/intake");
    } catch (e) {
      setError(e.message);
      setResetting(false);
    }
  }

  if (user === undefined) return <main className="card login"><p>Loading…</p></main>;

  if (!user) {
    return (
      <main className="card login">
        <h1>AI Career Strategist</h1>
        <p>Sign in to start or continue your career plan. Your profile is saved to your Google account.</p>
        <GoogleSignIn onCredential={signIn} />
        {error && <p className="error">{error}</p>}
      </main>
    );
  }

  return (
    <div className="shell">
      <header>
        <h1>AI Career Strategist</h1>
        <span className="user">
          {user.picture && <img className="avatar" src={user.picture} alt="" referrerPolicy="no-referrer" />}
          <span title={user.email}>{user.name}</span> ·{" "}
          <button className="link" onClick={() => { setError(""); setConfirmReset(true); }}>Start over</button> ·{" "}
          <button className="link" onClick={signOut}>Sign out</button>
        </span>
      </header>
      {confirmReset && (
        <div className="overlay">
          <div className="card dialog" role="alertdialog" aria-modal="true" aria-labelledby="reset-title">
            <h2 id="reset-title">Start over?</h2>
            <p>
              This permanently deletes your profile, chat, skill gaps, resource list and roadmap. You stay signed in.
              This can't be undone.
            </p>
            {error && <p className="error">{error}</p>}
            <div className="actions">
              <button className="secondary" onClick={() => setConfirmReset(false)} disabled={resetting} autoFocus>Cancel</button>
              <button className="danger" onClick={reset} disabled={resetting}>
                {resetting ? "Deleting…" : "Delete my data"}
              </button>
            </div>
          </div>
        </div>
      )}
      <StepIndicator />
      <Routes>
        <Route path="/" element={<Navigate to="/intake" replace />} />
        <Route path="/intake" element={<Intake />} />
        <Route path="/gaps" element={<SkillGaps />} />
        <Route path="/resources" element={<Resources />} />
        <Route path="/roadmap" element={<Roadmap />} />
      </Routes>
    </div>
  );
}
