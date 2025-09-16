// src/components/GratitudeCloud.jsx
import { useEffect, useMemo, useRef, useState } from 'react'
import { Box, Text } from 'grommet'
import cloud from 'd3-cloud'
import API from '../api'
import { useTheme } from 'styled-components'


// nice purple scale: darker for larger words
function colorFor(size, maxSize, theme) {
  const t = Math.max(0, Math.min(1, size / (maxSize || 1)))
  const base = theme.global?.colors?.brand || '#6366F1'
  // lighten for smaller words, darker for bigger
  const alpha = 0.4 + 0.6 * t
  return `${base}${Math.round(alpha * 255).toString(16).padStart(2, '0')}`
}

// helper: rough text width (monotone-ish, good enough for centering)
function estimateWidth(text, fontSize) {
  // average glyph ~0.55em for this font weight
  return text.length * fontSize * 0.55;
}

// helper: shift words so their bounding box is centered at 0,0
function centerWords(words) {
  if (!words.length) return words;

  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;

  for (const w of words) {
    const wHalf = estimateWidth(w.text, w.size) / 2;
    const hHalf = w.size * 0.5; // cap height approx
    const left   = w.x - wHalf;
    const right  = w.x + wHalf;
    const top    = w.y - hHalf;
    const bottom = w.y + hHalf;

    if (left   < minX) minX = left;
    if (top    < minY) minY = top;
    if (right  > maxX) maxX = right;
    if (bottom > maxY) maxY = bottom;
  }

  const cx = (minX + maxX) / 2;
  const cy = (minY + maxY) / 2;

  // shift so bbox center is (0,0)
  return words.map(w => ({ ...w, x: w.x - cx, y: w.y - cy }));
}


export default function GratitudeCloud({ height = 240 }) {
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [meta, setMeta] = useState(null)
  const [raw, setRaw] = useState([])          // [{word,count}]
  const [placed, setPlaced] = useState([])    // layout result

  function setPlacedAndLog(placed) {
    console.log('setting placed to', placed)
    setPlaced(placed)
  }

  // container sizing
  const ref = useRef(null)
  const [dims, setDims] = useState({ w: 0, h: height })
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([entry]) => {
        const w = Math.max(0, Math.floor(entry.contentRect.width));
        if (w > 0) {
        setDims({ w, h: height });
        // lock after first good measure
        ro.disconnect();
        }
    });
    ro.observe(ref.current);
    return () => ro.disconnect();
    }, [height]);


  // fetch data once
  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const res = await API.getGratitudeCloud()
        if (!alive) return
        setMeta({ start: res.period_start, end: res.period_end })
        setRaw(Array.isArray(res.cloud) ? res.cloud : [])
        setError(null)
      } catch (e) {
        setError(e.message || 'Failed to load')
        setRaw([])
      } finally {
        if (alive) setLoading(false)
      }
    })()
    return () => { alive = false }
  }, [])

  // compute font sizes from counts (stable, cheap)
  const words = useMemo(() => {
    if (!raw.length) return []
    const counts = raw.map(d => d.count)
    const cMin = Math.min(...counts)
    const cMax = Math.max(...counts)
    const scale = (c) => 12 + (c - cMin) / Math.max(1, cMax - cMin) * 36 // 12–48px
    return raw.map(d => ({ text: d.word, raw: d.count, size: scale(d.count) }))
  }, [raw])

  // run d3-cloud whenever we have size & words
  useEffect(() => {
  // only run once when we have words and a real box
  if (placed.length) return;
  if (!words.length || dims.w <= 0 || dims.h <= 0) return;

  let cancelled = false;
  const engine = cloud()
    .size([dims.w, dims.h])
    .words(words.map(w => ({ ...w })))
    .padding(2)
    .rotate(() => {
      const angles = [0, 90, 0, 270, 0]
      return angles[Math.floor(Math.random() * angles.length)]
    })
    .font('Inter, system-ui, -apple-system, Segoe UI, Roboto, sans-serif')
    .fontSize(d => d.size)
    .on('end', (out) => {
      if (cancelled) return;
      const centered = centerWords(out);
      setPlaced(centered);
    });

  engine.start();
  return () => { cancelled = true; try { engine.stop && engine.stop() } catch {} };
}, [words, dims.w, dims.h]); // no 'placed' dep


  const theme = useTheme()
  const maxSize = useMemo(() => (words.length ? Math.max(...words.map(w => w.size)) : 48), [words])


  return (
    <Box gap="xsmall">

      <Box
        ref={ref}
        round="small"
        pad="small"
        background="background"
        height={`${height}px`}
        overflow="hidden"
        style={{ position: 'relative' }}   // anchor for absolutely positioned words
      >
        {loading && <Text size="small" color="text-weak">Loading…</Text>}
        {!loading && !!error && <Text size="small" color="status-critical">{error}</Text>}
        {!loading && !error && placed.length === 0 && (
          <Text size="small" color="text-weak">No gratitude data yet</Text>
        )}

        {/* draw words */}
        {placed.map((w, i) => (
          <span
            key={`${w.text}-${i}`}
            title={`${w.text} (${w.raw})`}
            style={{
              position: 'absolute',
              left: (dims.w / 2) + w.x,
              top: (dims.h / 2) + w.y,
              transform: `translate(-50%, -50%) rotate(${w.rotate}deg)`,
              fontSize: `${Math.round(w.size)}px`,
              lineHeight: 1,
              fontWeight: 700,
              color: colorFor(w.size, maxSize, theme),
              whiteSpace: 'nowrap',
              userSelect: 'none',
              pointerEvents: 'none',
            }}
          >
            {w.text}
          </span>
        ))}
      </Box>
    </Box>
  )
}
