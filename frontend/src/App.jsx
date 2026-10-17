import { useCallback, useEffect, useMemo, useState } from "react";
import { Navigate, Outlet, Route, Routes, useNavigate } from "react-router-dom";
import { getIntake, getMe, googleLogin, logout, setUnauthorizedHandler, startOver } from "./api.js";
import ConfirmDialog from "./components/ConfirmDialog.jsx";
import { loadGis } from "./components/GoogleSignIn.jsx";
import Sidebar from "./components/Sidebar.jsx";
import ComingSoon from "./pages/ComingSoon.jsx";
import Home from "./pages/Home.jsx";
import Intake from "./pages/Intake.jsx";
import Resources from "./pages/Resources.jsx";
import Roadmap from "./pages/Roadmap.jsx";
import SkillGaps from "./pages/SkillGaps.jsx";
import { ProfileContext } from "./profileContext.js";

// The signed-in layout: sidebar on the left (a menu on a phone), the current page on the right.
function Shell({ user, profile, onStartOver, onSignOut }) {
  return (
    <div className="shell">
      <a className="skip-link" href="#main">Skip to content</a>
      <Sidebar user={user} profile={profile} onStartOver={onStartOver} onSignOut={onSignOut} />
      <main id="main" className="main" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  );
}

export default function App() {
  const [user, setUser] = useState(undefined); // undefined = checking session, null = signed out
  const [profile, setProfile] = useState(null); // for the sidebar's profile card
  const [error, setError] = useState("");
  const [confirmReset, setConfirmReset] = useState(false);
  const [resetting, setResetting] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    setUnauthorizedHandler(() => setUser(null));
    getMe()
      .then(setUser)
      .catch((e) => {
        setUser(null);
        if (e.status !== 401) setError(e.message);
      });
  }, []);

  useEffect(() => {
    if (!user) return setProfile(null);
    getIntake().then((s) => setProfile(s.profile)).catch(() => {});
  }, [user]);

  const signIn = useCallback(async (credential) => {
    setError("");
    try {
      setUser(await googleLogin(credential));
      // "Start Assessment": signing in on Home leads to Intake; a deep link stays where it is.
      if (window.location.pathname === "/") navigate("/intake");
    } catch (e) {
      setError(e.message);
    }
  }, [navigate]);

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

  const closeReset = useCallback(() => setConfirmReset(false), []);
  const shared = useMemo(() => ({ profile, setProfile }), [profile]);

  if (user === undefined) return <div className="center-screen"><p>Loading…</p></div>;
  if (!user) return <Home onCredential={signIn} error={error} />;

  const shell = (
    <Shell
      user={user}
      profile={profile}
      onStartOver={() => { setError(""); setConfirmReset(true); }}
      onSignOut={signOut}
    />
  );

  return (
    <ProfileContext.Provider value={shared}>
      {confirmReset && (
        <ConfirmDialog
          title="Start over?"
          confirmLabel="Delete my data"
          busyLabel="Deleting…"
          busy={resetting}
          error={error}
          onCancel={closeReset}
          onConfirm={reset}
        >
          <p>
            This permanently deletes your profile, chat, skill gaps, resource list and roadmap. You stay signed in.
            This can't be undone.
          </p>
        </ConfirmDialog>
      )}
      <Routes>
        <Route path="/" element={<Home user={user} />} />
        <Route element={shell}>
          <Route path="/intake" element={<Intake />} />
          <Route path="/gaps" element={<SkillGaps />} />
          <Route path="/resources" element={<Resources />} />
          <Route path="/roadmap" element={<Roadmap />} />
          <Route path="/dashboard" element={<ComingSoon title="Dashboard" subtitle="Your readiness, skill coverage and roadmap progress at a glance." milestone={11} />} />
          <Route path="/progress" element={<ComingSoon title="Progress Review" subtitle="Report what you finished and refresh your plan." milestone={11} />} />
          <Route path="/jobs" element={<ComingSoon title="Job Match" subtitle="Roles that fit the skills you have built." milestone={12} />} />
          <Route path="/resume" element={<ComingSoon title="Resume Optimizer" subtitle="Your resume, tailored to one job." milestone={13} />} />
          <Route path="*" element={<Navigate to="/intake" replace />} />
        </Route>
      </Routes>
    </ProfileContext.Provider>
  );
}
