import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import Button from "../components/Button.jsx";
import Card from "../components/Card.jsx";
import GoogleSignIn from "../components/GoogleSignIn.jsx";
import Icon, { Logo } from "../components/Icon.jsx";

const BENEFITS = [
  { icon: "person", title: "Personalized Career Strategy", text: "Built from your goal, your industry and the hours you really have." },
  { icon: "skills", title: "Skill Gap Analysis", text: "See what already transfers and which gaps matter most for your target role." },
  { icon: "roadmap", title: "AI Learning Roadmaps", text: "A week-by-week plan with real links and a portfolio project in every phase." },
  { icon: "jobs", title: "Job Matching", text: "Roles that fit the skills you have built. Coming soon." },
];

// How every roadmap is structured (no sample person or numbers).
const STEPS = [
  { when: "Months 1–2 · Phase 1", what: "Your highest-priority skill gaps first", project: "Portfolio project 1: a real problem from your industry" },
  { when: "Months 3–4 · Phase 2", what: "Applied skills, built on that foundation", project: "Portfolio project 2: built on a named public dataset" },
  { when: "Months 5–6 · Phase 3", what: "The remaining gaps, sized to your weekly hours", project: "Portfolio project 3: something to show in interviews" },
];

// The landing page. Signed out it carries the Google sign-in; signed in it links into the app.
export default function Home({ user, onCredential, error }) {
  const [asked, setAsked] = useState(false); // Start Assessment was pressed while signed out
  const signIn = useRef(null);

  // Google only accepts a click on its own button, so ours points the user to it.
  function showSignIn() {
    setAsked(true);
    signIn.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    signIn.current?.focus();
  }

  return (
    <div className="home">
      <header className="home-inner home-header">
        <Link to="/" className="brand">
          <Logo />
          <span>AI Career Strategist</span>
        </Link>
        {user ? (
          <Button variant="secondary" to="/intake">Open my plan</Button>
        ) : (
          <Button variant="secondary" onClick={showSignIn}>Sign in</Button>
        )}
      </header>

      <main>
        <section className="home-inner hero">
          <div className="hero-text">
            <div className="hero-eyebrow">For engineers, architects and analysts moving into AI</div>
            <h1>AI Career Strategist</h1>
            <p className="hero-sub">From “I want to move into AI” to a realistic 6-month roadmap.</p>
            <div className="row">
              {user ? <Button to="/intake">Start Assessment</Button> : <Button onClick={showSignIn}>Start Assessment</Button>}
              <Button variant="secondary" disabled aria-describedby="demo-note">View Demo</Button>
            </div>
            <p className="muted" id="demo-note">Takes a few minutes: five questions to start. The demo is coming soon.</p>
            {!user && (
              <div className={`card signin ${asked ? "card-highlight" : "card-outlined"}`} tabIndex={-1} ref={signIn}>
                <strong>{asked ? "Sign in with Google to start your assessment" : "Sign in to start or continue your plan"}</strong>
                <p className="muted">Your profile and plan are saved to your Google account.</p>
                <GoogleSignIn onCredential={onCredential} />
                {error && <p className="error" role="alert">{error}</p>}
              </div>
            )}
          </div>

          <Card as="div" outlined className="hero-card">
            <div className="card-head">
              <h2>How it works</h2>
              <span className="muted">Your hours · 26 weeks</span>
            </div>
            <p>Tell us your current role, your target AI role and your weekly hours. You get:</p>
            {STEPS.map((s) => (
              <div key={s.when} className="step">
                <div className="step-when">{s.when}</div>
                <div className="step-what">{s.what}</div>
                <div className="muted">{s.project}</div>
              </div>
            ))}
          </Card>
        </section>

        <section className="home-inner benefits card-row card-row-narrow" aria-label="Benefits">
          {BENEFITS.map((b) => (
            <Card as="div" key={b.title} className="benefit">
              <Icon name={b.icon} size={24} />
              <h2>{b.title}</h2>
              <p>{b.text}</p>
            </Card>
          ))}
        </section>

        <div className="home-inner home-info card-row card-row-narrow">
          <section id="about">
            <h2>About</h2>
            <p>
              AI Career Strategist helps technology professionals plan a move into AI roles: a profile, a skill-gap
              analysis, vetted learning resources and a six-month roadmap sized to your weekly hours.
            </p>
          </section>
          <section id="contact">
            <h2>Contact</h2>
            <p>Contact details will be added here.</p>
          </section>
          <section id="privacy">
            <h2>Privacy</h2>
            <p>
              You sign in with Google; we keep your name, email and profile picture, your answers and the plans
              built from them. Your answers are sent to an AI service to build those plans. “Start over” deletes
              your profile, chat, skill gaps, resources and roadmap.
            </p>
          </section>
        </div>
      </main>

      <footer className="home-footer">
        <div className="home-inner">
          <div>AI Career Strategist</div>
          <nav aria-label="Footer">
            <a href="#about">About</a>
            <a href="#contact">Contact</a>
            <a href="#privacy">Privacy</a>
          </nav>
        </div>
      </footer>
    </div>
  );
}
