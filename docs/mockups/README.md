# UI mockups

Static HTML mockups of the nine screens in `docs/Career_Strategist_Product_Requirement_Document.docx`,
in the PRD's dark design. They are the visual reference for the React frontend from milestone 7 onwards.
Open `index.html` in a browser; the sidebar links move between screens.

## Screens

| File | Screen | SPEC.md section | Built in milestone |
|---|---|---|---|
| `index.html` | Home (before sign-in) | 1. Home | 7 |
| `intake.html` | Intake | 2. Intake | 7 (restyle), 8 (new fields, resume upload) |
| `dashboard.html` | Dashboard | 4. Dashboard | 11 |
| `skill-analysis.html` | Skill Analysis | 5. Skill Analysis | 7 (restyle), 8 (resume evidence, gap chart) |
| `roadmap.html` | Learning Roadmap | 7. Learning Roadmap | 7 (restyle), 10 (tracking, dates, PDF) |
| `resources.html` | Resources | 6. Resources | 7 (restyle), 9 (YouTube, filters, Save/Start/Complete) |
| `progress-review.html` | Progress Review | 9. Progress Review | 11 |
| `job-match.html` | Job Match | 10. Job Match | 12 |
| `resume-optimizer.html` | Resume Optimizer | 11. Resume Optimizer | 13 |

Milestone 7 builds the app shell (sidebar, Home, design tokens) and restyles the four existing pages to match
these mockups. Screens for later milestones show where the shell and components are heading; build their
behavior only in their own milestone.

## How to use them

- **Match the look, not the markup.** The mockups use inline styles so each file stands alone. In React, build
  reusable components and use the variables in `design-tokens.css`; don't copy inline styles.
- **Reusable components** that appear across screens: Sidebar (active item, profile card at the bottom),
  PageHeader (title, subtitle, actions), Card, MetricCard, SkillBadge (skill / gap / done / assumed),
  Button (primary, secondary, text), FilterChip (pressed state), ResourceCard, Timeline (phase, collapsible
  month, week, task row with checkbox), Chat (assistant and user bubbles, input), ProgressBar, JobTable and
  JobDetail, ResumeComparison.
- **Layout:** sidebar and main content in a wrapping flex row, so on a phone the sidebar stacks above the
  content (make it a collapsible menu in React). Cards wrap rather than shrink. Wide tables scroll inside
  their card. Every page fits a 390 px wide screen without sideways scrolling.
- **Accessibility:** real `<button>`, `<a>`, `<input>` and `<label>` elements, 44 px minimum touch targets,
  `aria-current="page"` on the active nav item, `aria-pressed` on toggle chips, visible focus outlines.
  Primary buttons use dark text on `#00B5FF` because white text on that blue fails contrast.
- **Charts:** the radar and line charts on the Dashboard are hand-drawn SVG here. In React use Recharts
  (SPEC.md tech stack) with the same colors: today/current in `--color-primary`, target or planned dashed.

## Sample data

All numbers, dates and names are sample data for one example user (Solution Architect in FinTech moving to
AI Architect, 7 hours a week). Text in square brackets, such as `[Company A]`, `[salary]`, `[rating]` or
`[Employer]`, is a placeholder for real data from the API. Never ship sample values in the app.

The Resume Optimizer screen shows the no-invention rule from SPEC.md: employers and dates come only from the
user's resume, and projects the user hasn't done yet are listed separately, not added to the resume.

## Not covered yet

- The AI Career Transition Report view (SPEC.md section 8) has no mockup. It was built in milestone 10 at
  `/report` (sidebar item "Transition Report") with the same card and type styles; the Dashboard's "View
  Transition Report" button links to it (milestone 11).
- The Dashboard radar shows the plan's skill gaps rather than the five capability areas (only gaps have a
  saved target level). Jobs Applied counts the jobs marked as applied on Job Match (milestone 12).
- Job Match: work mode and location are search inputs; the detail panel sits beside the table on desktop
  and below it on a phone. Update Resume opens the Resume Optimizer, which arrives in milestone 13.
- Sign-in, loading, error and empty states. Use the existing progress messages and error handling, restyled
  with these tokens.
