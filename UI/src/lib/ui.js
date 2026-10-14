// Chart sizing that fits a phone first.
export function chartDims() {
  const w = typeof window !== 'undefined' ? window.innerWidth : 390
  const narrow = w < 500
  return {
    hArea: narrow ? 220 : 280,
    hLine: narrow ? 180 : 240,
    tick: narrow ? 10 : 12,
    yLeftPad: narrow ? 32 : 44,
    margin: { top: 8, right: 8, bottom: 0, left: 0 },
  }
}
