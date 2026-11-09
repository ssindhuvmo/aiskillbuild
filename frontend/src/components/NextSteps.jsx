import { formatDay } from "../tracking.js";

// The roadmap's immediate next steps (tracking.next_steps): overdue first, with hours and due date.
export default function NextSteps({ steps }) {
  if (!steps.length) return <p>Every task is done. Well done!</p>;
  return (
    <ol className="next-steps">
      {steps.map((step) => (
        <li key={step.task_id}>
          <span>
            {step.title}
            {step.resource && (
              <>
                {" · "}
                <a href={step.resource.url} target="_blank" rel="noopener noreferrer">{step.resource.title} ↗</a>
              </>
            )}
          </span>
          <span className={step.overdue ? "next-step-meta overdue" : "next-step-meta"}>
            {step.hours} h · {step.overdue ? `overdue since ${formatDay(step.due)}` : `week ${step.week}, due ${formatDay(step.due)}`}
          </span>
        </li>
      ))}
    </ol>
  );
}
