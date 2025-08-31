// src/pages/DayLog.jsx
import { useEffect, useMemo, useRef, useState } from 'react'
import { Box, Button, Heading, Text } from 'grommet'
import DotRail from '../components/DotRail'
import MoodSlider from '../components/MoodSlider'
import BottomNav from '../components/BottomNav'
import BigTextArea from '../components/BigTextArea'
import API from '../api'
import { useLocation, useNavigate } from 'react-router-dom'
import { localISODate } from '../lib/date'


const RAIL_W = 36;              // px, thin rail
const HEADER_PX = 116;          // offset where rail should start (below banner + heading)
const BOTTOM_NAV_PX = 72;       // your bottom bar

function todaysGratitudeCount() {
  const d = new Date()
  const key = `${d.getFullYear()}-${d.getMonth()+1}-${d.getDate()}`
  let hash = 0; for (let i=0;i<key.length;i++) hash = (hash*31 + key.charCodeAt(i)) % 1000
  return 2 + (hash % 3)
}

function visibleRatio(el, container) {
  if (!el || !container) return 0
  const er = el.getBoundingClientRect()
  const cr = container.getBoundingClientRect()
  const top = Math.max(er.top, cr.top)
  const bottom = Math.min(er.bottom, cr.bottom)
  const visible = Math.max(0, bottom - top)
  const total = er.height || 1
  return visible / total
}

function computeDarkCount(sections, container, prevDark) {
  // Find the lowest section with >= 85% visible
  let lastIdx = -1
  sections.forEach((s, idx) => {
    const ratio = visibleRatio(s.ref.current, container)
    if (ratio >= 0.85) lastIdx = idx
  })
  if (lastIdx >= 0) return lastIdx   // darken up to (lastIdx - 1) in your DotRail logic

  // Fallback: if none qualify, keep previous value so dots never "disappear"
  return prevDark
}

export default function DayLog() {
  const nav = useNavigate()
  const location = useLocation()
  const initial = location.state?.initial || null
  const dayISO = location.state?.day || localISODate()

  const n = useMemo(() => todaysGratitudeCount(), [])
  const [summary, setSummary] = useState(initial?.summary || '')
  const [highs, setHighs]     = useState(initial?.highs || '')
  const [lows, setLows]       = useState(initial?.lows || '')
  const [buffs, setBuffs]     = useState(initial?.buffalos || '')
  const [mood, setMood]       = useState(initial?.mood ?? 3)
  const [grat, setGrat]       = useState(
    Array.isArray(initial?.gratitude) && initial.gratitude.length
      ? initial.gratitude
      : Array.from({ length: todaysGratitudeCount() }, () => '')
  )
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (initial) return
    (async () => {
      try {
        const res = await API.getDayLog(dayISO)
        if (res?.found) {
          const r = res.reflection
          setSummary(r.summary || '')
          setHighs(r.highs || '')
          setLows(r.lows || '')
          setBuffs(r.buffalos || '')
          setMood(r.mood ?? 3)
          setGrat(Array.isArray(r.gratitude) ? r.gratitude : [])
        }
      } catch {}
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // refs for sections to observe (7 dots)
  const refs = {
    summary: useRef(null),
    highs: useRef(null),
    lows: useRef(null),
    buffs: useRef(null),
    mood: useRef(null),
    grat1: useRef(null),
    gratN: useRef(null),
  }
  const sections = [
    { key: 'summary', ref: refs.summary },
    { key: 'highs',   ref: refs.highs   },
    { key: 'lows',    ref: refs.lows    },
    { key: 'buffs',   ref: refs.buffs   },
    { key: 'mood',    ref: refs.mood    },
    { key: 'grat1',   ref: refs.grat1   },
    { key: 'gratN',   ref: refs.gratN   },
  ]

  // scroll container ref (so IO watches that *container*, not the window)
  const scrollRef = useRef(null)
  const [darkCount, setDarkCount] = useState(0)

  useEffect(() => {
    const scroller = scrollRef.current
    if (!scroller) return

    const onScroll = () => {
      setDarkCount(prev => computeDarkCount(sections, scroller, prev))
    }

    // initial & listeners
    onScroll()
    scroller.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => {
      scroller.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const isUpdate = Boolean(initial)

  const canSubmit =
    summary.trim() || highs.trim() || lows.trim() || buffs.trim() || grat.some(g => g.trim())


  const submit = async () => {
    if (!canSubmit) return
    setSubmitting(true); setError(null)
    try {
      const res = await API.createDayLog({ summary, highs, lows, buffalos: buffs, mood, gratitude: grat, day: dayISO })
      if (res) {
        nav('/dashboard', { replace: true, state: { toast: isUpdate ? 'Updated!' : 'Saved!' }})
      }
    } catch (e) {
      setError(e.message || 'Failed to save'); setSubmitting(false)
    }
  }

  return (
    <Box fill pad={{ bottom: `${BOTTOM_NAV_PX}px` }} style={{ position: 'relative' }}>
      {/* Header stays static */}
      <Box pad={{ top: 'medium', horizontal: 'medium' }}>
        <Heading level={3} margin={{ bottom: 'xxsmall' }}>Day Log</Heading>
        <Text color="text-weak" margin={{ bottom: 'small' }}>Quick reflection for today.</Text>
      </Box>

      {/* Fixed dot rail on the left */}
      <Box
        width={`${RAIL_W}px`}
        align="center"
        style={{
          position: 'fixed',
          left: `calc(env(safe-area-inset-left, 0px) + 6px)`,
          top: `${HEADER_PX}px`,
          bottom: `${BOTTOM_NAV_PX}px`,
          zIndex: 2,
        }}
      >
        <DotRail total={7} darkCount={darkCount + 1} topPx={0} />
      </Box>

      {/* Scrollable form column */}
      <Box
        ref={scrollRef}
        style={{
          marginLeft: `calc(${RAIL_W}px + 8px)`,
          height: `calc(100vh - ${HEADER_PX}px - ${BOTTOM_NAV_PX}px)`,
          overflowY: 'auto',
          WebkitOverflowScrolling: 'touch',
        }}
        pad={{ horizontal: 'medium' }}
      >
        <BigTextArea
          innerRef={refs.summary}
          label="Day Summary"
          value={summary}
          onChange={setSummary}
          placeholder="How did the day go?"
        />
        <BigTextArea
          innerRef={refs.highs}
          label="Today's High(s)"
          value={highs}
          onChange={setHighs}
          placeholder="Wins, highlights..."
        />
        <BigTextArea
          innerRef={refs.lows}
          label="Today's Low(s)"
          value={lows}
          onChange={setLows}
          placeholder="What was tough?"
        />
        <BigTextArea
          innerRef={refs.buffs}
          label="Today's Buffalo(s)"
          value={buffs}
          onChange={setBuffs}
          placeholder="Odd/interesting things…"
        />

        <Box ref={refs.mood} style={{height: 'clamp(240px, 32vh, 520px)'}}>
          <MoodSlider value={mood} onChange={setMood} />
        </Box>

        <Box height="180px" flex={false} />   {/* spacer to ensure no overlap - 160 for the component, 20 to breath*/}



        <Text size="small" weight={700} color="text-weak" margin={{ top: 'xsmall', bottom: 'small' }}>
          {n} things you’re grateful for right now
        </Text>

        <BigTextArea
          innerRef={refs.grat1}
          label="Grateful #1"
          value={grat[0]}
          onChange={v => setGrat(prev => prev.map((x, i) => (i === 0 ? v : x)))}
          placeholder="People, moments, comforts…"
        />

        {/* middle gratitude items */}
        {Array.from({ length: Math.max(0, n - 2) }).map((_, k) => {
          const i = k + 1
          if (i === n - 1) return null
          return (
            <BigTextArea
              key={i}
              label={`Grateful #${i + 1}`}
              value={grat[i]}
              onChange={v => setGrat(prev => prev.map((x, j) => (j === i ? v : x)))}
              placeholder="People, moments, comforts…"
            />
          )
        })}

        <BigTextArea
          innerRef={refs.gratN}
          label={`Grateful #${n}`}
          value={grat[n - 1]}
          onChange={v => setGrat(prev => prev.map((x, i) => (i === n - 1 ? v : x)))}
          placeholder="People, moments, comforts…"
        />

        {error && <Text color="status-critical">{error}</Text>}
        <Button
          primary
          label={submitting ? 'Saving…' : 'Save day log'}
          disabled={!canSubmit || submitting}
          onClick={submit}
          margin={{ top: 'small', bottom: 'medium' }}
        />
      </Box>

      <Box height="80px" flex={false} />   {/* spacer to ensure submit button is easily visible on mobile */}


      <BottomNav />
    </Box>
  )
}
