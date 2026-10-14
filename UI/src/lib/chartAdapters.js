// Shape the analytics endpoints for recharts.
const dayOf = b => (typeof b === 'string' ? b : (b?.day || b?.date || ''))

// /analytics/points_by_category -> { rows: [{date, cat_<id>: cum, ...}], catMeta: {id: {...}} }
export function adaptCategorySeries(res) {
  const buckets = res?.buckets || []
  const series = res?.series || {}
  const catMeta = {}
  for (const c of res?.categories || []) catMeta[c.id] = c
  const rows = buckets.map((b, idx) => {
    const row = { date: dayOf(b) }
    for (const [cid, vals] of Object.entries(series)) row[`cat_${cid}`] = vals?.[idx] ?? 0
    return row
  })
  return { rows, catMeta }
}

// /analytics/points_over_time -> [{date, value}] (running net points)
export function adaptTotalSeries(res) {
  return (res?.buckets || []).map(b => ({ date: dayOf(b), value: Number(b?.cum ?? b?.net ?? 0) }))
}
