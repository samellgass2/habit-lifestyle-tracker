// Feature flags for the hosted build.
// The social layer (friends, feed, gifts, inbox) has been unused since spring
// 2026; its API and data stay, the UI is hidden unless VITE_SOCIAL=1.
export const SOCIAL = import.meta.env.VITE_SOCIAL === '1'
