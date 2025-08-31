// src/theme/dynamicTheme.js
// time-of-day buckets (local)
function todBucket(date = new Date()) {
  const h = date.getHours()
  if (h < 6) return 'night'
  if (h < 11) return 'morning'
  if (h < 17) return 'day'
  if (h < 21) return 'evening'
  return 'night'
}

// meteorological seasons (northern hemisphere)
function season(date = new Date()) {
  const m = date.getMonth() + 1
  if (m >= 3 && m <= 5) return 'spring'
  if (m >= 6 && m <= 8) return 'summer'
  if (m >= 9 && m <= 11) return 'fall'
  return 'winter'
}

// tiny HSL helpers
const clamp = (n, a, b) => Math.max(a, Math.min(b, n))
function hsl(h, s, l) { return `hsl(${h}deg ${s}% ${l}%)` }
function vib(l, by) { return clamp(l + by, 5, 95) } // adjust lightness

// base hues per season
const seasonHue = {
  spring: 140, // green-teal
  summer: 205, // sky blue
  fall:   30,  // amber
  winter: 260, // indigo
}

export function computeTheme(now = new Date()) {
  const s = season(now)
  const t = todBucket(now)
  const hue = seasonHue[s]

  const baseS = { spring: 55, summer: 60, fall: 65, winter: 50 }[s]
  const baseL = { spring: 55, summer: 52, fall: 50, winter: 47 }[s]
  const lShift = { night: -12, morning: +8, day: 0, evening: -6 }[t]
  const sShift = { night: -10, morning: +5, day: 0, evening: -5 }[t]

  const primary = hsl(hue, clamp(baseS + sShift, 35, 80), vib(baseL, lShift))
  const primaryWeak = hsl(hue, clamp(baseS + sShift - 15, 25, 70), vib(baseL, lShift + 12))
  const bg = t === 'night' ? hsl(hue, 20, 7) : hsl(hue, 20, 98)
  const text = t === 'night' ? hsl(hue, 10, 92) : hsl(hue, 25, 12)
  const subtle = t === 'night' ? hsl(hue, 12, 18) : hsl(hue, 16, 92)
  const critical = hsl(8, 75, t === 'night' ? 55 : 45)
  const ok = hsl(145, 55, t === 'night' ? 55 : 40)

  return {
    name: `seasonal-${s}-${t}`,
    global: {
      colors: {
        brand: primary,
        'accent-1': primaryWeak,
        background: bg,
        text,
        'text-weak': hsl(seasonHue[s], 10, t === 'night' ? 70 : 35),
        border: subtle,
        focus: primary,
        'status-critical': critical,
        'status-ok': ok,
      },
      font: {
        family: 'Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif',
        size: '16px',
        height: '1.35'
      }
    },
    button: {
      primary: { color: 'brand' },
      border: { radius: '12px', color: 'border' },
      padding: { horizontal: '20px', vertical: '10px' }
    },
    card: {
      container: {
        round: 'large',
        elevation: 'small',
        border: { color: 'border' }
      },
      header: { pad: { horizontal: 'medium', vertical: 'small' } },
      body: { pad: { horizontal: 'medium', vertical: 'medium' } },
      footer: { pad: { horizontal: 'medium', vertical: 'small' } },
    },
    formField: {
      border: { round: '10px' },
      margin: 'xsmall'
    }
  }
}

