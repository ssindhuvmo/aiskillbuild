// A toggle chip; `pressed` is announced through aria-pressed.
export default function FilterChip({ pressed = false, children, ...props }) {
  return (
    <button type="button" className="chip" aria-pressed={pressed} {...props}>
      {children}
    </button>
  );
}
