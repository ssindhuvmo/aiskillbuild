// A banner for "out of date" states and other things the user should know before acting.
export default function Notice({ children }) {
  return <div className="notice" role="status">{children}</div>;
}
