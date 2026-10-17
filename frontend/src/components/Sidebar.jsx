import { useEffect, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import Button from "./Button.jsx";
import Icon, { Logo } from "./Icon.jsx";

// SPEC.md "Navigation". NavLink sets aria-current="page" on the active item.
const NAV = [
  { to: "/", label: "Home", icon: "home" },
  { to: "/intake", label: "Intake", icon: "intake" },
  { to: "/dashboard", label: "Dashboard", icon: "dashboard" },
  { to: "/gaps", label: "Skill Analysis", icon: "skills" },
  { to: "/roadmap", label: "Learning Roadmap", icon: "roadmap" },
  { to: "/resources", label: "Resources", icon: "resources" },
  { to: "/progress", label: "Progress Review", icon: "progress" },
  { to: "/jobs", label: "Job Match", icon: "jobs" },
  { to: "/resume", label: "Resume Optimizer", icon: "resume" },
];

export default function Sidebar({ user, profile, onStartOver, onSignOut }) {
  const [open, setOpen] = useState(false); // only matters on a phone, where the menu collapses
  const { pathname } = useLocation();

  useEffect(() => setOpen(false), [pathname]);

  const roles = [profile?.current_role, profile?.target_role].filter(Boolean);
  const meta = [profile?.domain, profile?.hours_per_week && `${profile.hours_per_week} hrs/week`].filter(Boolean);

  return (
    <nav className="sidebar" aria-label="Main">
      <div className="sidebar-top">
        <Link to="/" className="brand">
          <Logo />
          <span>AI Career Strategist</span>
        </Link>
        <Button variant="secondary" className="menu-toggle" aria-expanded={open} aria-controls="sidebar-menu" onClick={() => setOpen(!open)}>
          <Icon name={open ? "close" : "menu"} />
          Menu
        </Button>
      </div>
      <div id="sidebar-menu" className={`sidebar-menu${open ? " open" : ""}`}>
        <ul className="nav-list">
          {NAV.map((item) => (
            <li key={item.to}>
              <NavLink to={item.to} end className="nav-item">
                <Icon name={item.icon} />
                <span>{item.label}</span>
              </NavLink>
            </li>
          ))}
        </ul>
        <div className="profile-card">
          <div className="profile-card-label">Profile</div>
          <div className="profile-card-name">
            {user.picture && <img className="avatar" src={user.picture} alt="" referrerPolicy="no-referrer" />}
            <span title={user.email}>{user.name}</span>
          </div>
          <div>{roles.length ? roles.join(" → ") : "Profile not started yet"}</div>
          {meta.length > 0 && <div className="profile-card-meta">{meta.join(" · ")}</div>}
          <div className="profile-card-actions">
            <Button variant="text" onClick={onStartOver}>Start over</Button>
            <Button variant="text" onClick={onSignOut}>Sign out</Button>
          </div>
        </div>
      </div>
    </nav>
  );
}
