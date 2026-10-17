import { Link } from "react-router-dom";

// variant: primary | secondary | text | quiet | danger. With `to` it renders a router link.
export default function Button({ variant = "primary", to, className = "", ...props }) {
  const cls = `btn btn-${variant} ${className}`.trim();
  return to ? <Link to={to} className={cls} {...props} /> : <button type="button" className={cls} {...props} />;
}
