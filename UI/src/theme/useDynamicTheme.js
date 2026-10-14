// src/theme/useDynamicTheme.js
import { useEffect, useMemo, useState } from 'react'
import { computeTheme } from './dynamicTheme'

export default function useDynamicTheme(refreshMs = 5 * 60 * 1000) {
  const [now, setNow] = useState(new Date() || '')
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), refreshMs)
    return () => clearInterval(id)
  }, [refreshMs])
  return useMemo(() => computeTheme(now), [now])
}
