// The stroke icons from docs/mockups, drawn on a 24px grid.
const PATHS = {
  home: "M3 11l9-8 9 8v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z",
  intake: "M4 5h16v11H9l-5 4z",
  dashboard: "M4 4h7v7H4zM13 4h7v4h-7zM13 11h7v9h-7zM4 14h7v6H4z",
  skills: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  roadmap: "M5 4v16M5 6h11l-2 3 2 3H5",
  resources: "M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3zM5 17a3 3 0 0 1 3-3h11",
  progress: "M4 12l5 5L20 6",
  jobs: "M3 8h18v12H3zM9 8V5h6v3",
  resume: "M6 3h9l4 4v14H6zM9 12h7M9 16h7",
  report: "M5 3h14v18H5zM9 8h6M9 12h6M9 16h3",
  feedback: "M4 5h16v11H9l-5 4zM8 9h8M8 12h5",
  fileDone: "M6 3h9l4 4v14H6zM9 14l2.5 2.5L16 12",
  person: "M12 4a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM4 21c0-4 4-6 8-6s8 2 8 6",
  menu: "M4 7h16M4 12h16M4 17h16",
  close: "M6 6l12 12M18 6L6 18",
};

export default function Icon({ name, size = 18 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}

export function Logo({ size = 28 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 28 28" fill="none" aria-hidden="true">
      <rect x="1" y="1" width="26" height="26" rx="8" fill="var(--color-primary)" />
      <path d="M7 19l5-6 4 3 5-8" stroke="var(--color-on-primary)" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
