import { localISODate } from '../lib/date'

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

// src/theme/dynamicTheme.js
export function computeTheme(now = new Date()) {
  const localDay = localISODate(now) // "YYYY-MM-DD" in local tz

  // reconstruct a Date object at midnight local for consistency
  const [y, m, d] = localDay.split('-').map(Number)
  const localNow = new Date(y, m - 1, d, now.getHours(), now.getMinutes(), now.getSeconds())

  const s = season(localNow)
  const t = todBucket(localNow)
  const hue = seasonHue[s]
  const isNight = t === 'night'
  console.log("starting up theme. We have now as ", localNow, "with season and date: ", s, t)


  const baseS = { spring: 55, summer: 60, fall: 65, winter: 50 }[s]
  const baseL = { spring: 55, summer: 52, fall: 50, winter: 47 }[s]
  const lShift = { night: -12, morning: +8, day: 0, evening: -6 }[t]
  const sShift = { night: -10, morning: +5, day: 0, evening: -5 }[t]

  const primary = hsl(hue, clamp(baseS + sShift, 35, 80), vib(baseL, lShift))
  const primaryWeak = hsl(hue, clamp(baseS + sShift - 15, 25, 70), vib(baseL, lShift + 12))
  const bg = isNight ? hsl(hue, 20, 7) : hsl(hue, 20, 98)
  const text = isNight ? hsl(hue, 10, 92) : hsl(hue, 25, 12)
  const subtle = isNight ? hsl(hue, 12, 18) : hsl(hue, 16, 92)
  const critical = hsl(8, 75, isNight ? 55 : 45)
  const ok = hsl(145, 55, isNight ? 55 : 40)

  const theme = {
    name: `seasonal-${s}-${t}`,
    global: {
      colors: {
        brand: primary,
        'accent-1': primaryWeak,
        background: bg,
        'background-back': bg,
        'background-contrast': isNight ? hsl(hue, 15, 11) : hsl(hue, 15, 96),

        text,
        'text-strong': text,
        'text-weak': hsl(hue, 10, isNight ? 70 : 35),
        'text-xweak': hsl(hue, 8, isNight ? 55 : 45),

        border: subtle,
        focus: primary,
        'status-critical': critical,
        'status-ok': ok,
        placeholder: isNight ? hsl(hue, 8, 55) : hsl(hue, 8, 45),
        control: text, // icon color (e.g., menu dots) follows text
      },
      font: {
        family: 'Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif',
        size: '16px',
        height: '1.35',
      },
    },
    button: {
      primary: { color: 'brand' },
      border: { radius: '12px', color: 'border' },
      padding: { horizontal: '20px', vertical: '10px' },
    },
    card: {
      container: {
        round: 'large',
        elevation: 'small',
        border: { color: 'border' },
        background: 'background',
      },
      header: { pad: { horizontal: 'medium', vertical: 'small' } },
      body: { pad: { horizontal: 'medium', vertical: 'medium' } },
      footer: { pad: { horizontal: 'medium', vertical: 'small' } },
    },
    formField: {
      border: { round: '10px' },
      margin: 'xsmall',
      label: { color: 'text-weak' },
    },
  }

  // Return both theme and mode
  return { theme, mode: isNight ? 'dark' : 'light' }
}

