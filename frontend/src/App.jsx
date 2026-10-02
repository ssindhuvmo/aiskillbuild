import { useCallback, useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { getMe, googleLogin, logout, setUnauthorizedHandler } from "./api.js";
import GoogleSignIn, { loadGis } from "./components/GoogleSignIn.jsx";
import StepIndicator from "./components/StepIndicator.jsx";
import Intake from "./pages/Intake.jsx";
import Placeholder from "./pages/Placeholder.jsx";
import Resources from "./pages/Resources.jsx";
import SkillGaps from "./pages/SkillGaps.jsx";

export default function App() {
  const [user, setUser] = useState(undefined); // undefined = checking session, null = signed out
  const [error, setError] = useState("");

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
          <span title={user.email}>{user.name}</span> · <button className="link" onClick={signOut}>Sign out</button>
        </span>
      </header>
      <StepIndicator />
      <Routes>
        <Route path="/" element={<Navigate to="/intake" replace />} />
        <Route path="/intake" element={<Intake />} />
        <Route path="/gaps" element={<SkillGaps />} />
        <Route path="/resources" element={<Resources />} />
        <Route path="/roadmap" element={<Placeholder title="Roadmap" />} />
      </Routes>
    </div>
  );
}
