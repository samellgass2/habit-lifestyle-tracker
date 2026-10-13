// Local calendar dates as "YYYY-MM-DD" (the user's own timezone, not UTC).
// Rebuilt 2026-10-12: src/lib was never committed (the root .gitignore's
// Python `lib/` rule swallowed it), so a fresh checkout could not build.
export function localISODate(d = new Date()) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}
