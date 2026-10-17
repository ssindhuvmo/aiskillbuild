// A rounded surface. `label` is the small accent line above, `title` the card heading.
export default function Card({ as: Tag = "section", title, label, outlined, className = "", children, ...props }) {
  return (
    <Tag className={`card${outlined ? " card-outlined" : ""} ${className}`.trim()} {...props}>
      {label && <div className="card-label">{label}</div>}
      {title && <h2>{title}</h2>}
      {children}
    </Tag>
  );
}
