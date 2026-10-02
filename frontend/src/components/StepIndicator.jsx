import { NavLink } from "react-router-dom";

const STEPS = [
  { to: "/intake", label: "Intake", ready: true },
  { to: "/gaps", label: "Skill Gaps", ready: true },
  { to: "/resources", label: "Resources", ready: true },
  { to: "/roadmap", label: "Roadmap" },
];

export default function StepIndicator() {
  return (
    <nav className="steps">
      {STEPS.map((s, i) => (
        <NavLink key={s.to} to={s.to} className={({ isActive }) => `step${isActive ? " active" : ""}${s.ready ? "" : " later"}`}>
          <span className="num">{i + 1}</span> {s.label}
        </NavLink>
      ))}
    </nav>
  );
}
