import { useEffect, useState, useMemo } from 'react'
import { Box, Button, Text } from 'grommet'
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid
} from 'recharts'
import API from '../api'
import { adaptCategorySeries } from '../lib/chartAdapters'
import { localISODate } from '../lib/date'
import { chartDims } from '../lib/ui'
import { darken } from '../lib/colors'

const fmtDay = (iso) => (iso?.length >= 10 ? iso.slice(5) : iso)

export default function PointsByCategoryChart({ height }) {
  const [period, setPeriod] = useState('week')
  const [anchor] = useState(localISODate())
  const [data, setData] = useState([])
  const [catMeta, setCatMeta] = useState({})
  const [focusedId, setFocusedId] = useState(null)
  const dims = chartDims()
  const H = height ?? dims.hArea
  console.log("pointsbycategory: height set to ", H)

  useEffect(() => {
    let alive = true
    API.getPointsByCategory(period, anchor).then(res => {
      if (!alive) return
      const { rows, catMeta } = adaptCategorySeries(res)
      setData(rows); setCatMeta(catMeta)
    }).catch(() => alive && (setData([]), setCatMeta({})))
    return () => { alive = false }
  }, [period, anchor])

  const catIds = useMemo(() => Object.keys(catMeta).map(Number), [catMeta])

  return (
    <Box gap="xsmall">
        <Box direction="row" justify="between" align="center" margin={{ bottom: 'xsmall' }}>
            <Text weight="bold">Habit tracking</Text>
            <Box direction="row" gap="xxsmall">
            <Button size="small" primary={period==='week'} label="Week" onClick={() => setPeriod('week')} />
            <Button size="small" primary={period==='month'} label="Month" onClick={() => setPeriod('month')} />
            </Box>
        </Box>

        <Box
            background="background"
            round="small"
            pad="xsmall"
            >
            <Box height={`${H}px`}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={data} margin={dims.margin}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" tick={{ fontSize: dims.tick }} tickFormatter={fmtDay}/>
                    <YAxis tick={{ fontSize: dims.tick }} width={dims.yLeftPad} />
                    <Tooltip formatter={(v) => [`${v} pts`, '']} />

                    {catIds.map(cid => {
                      const c = catMeta[cid] || {}
                      const show = !focusedId || focusedId === cid
                      if (!show) return null
                      const stroke = darken(c.color || '#999', -70)
                      return (
                        <Area
                          key={cid}
                          type="monotone"
                          dataKey={`cat_${cid}`}
                          name={`${c.emoji || ''} ${c.name || 'Category'}`}
                          stackId="1"
                          stroke={stroke}
                          strokeWidth={2}
                          fill={c.color || '#999'}
                          fillOpacity={0.30}
                          dot={false}
                          isAnimationActive={true}
                        />
                      )
                    })}
                  </AreaChart>
                </ResponsiveContainer>
            </Box>

            {/* compact legend inside the same card */}
            <Box direction="row" wrap gap="xxsmall" margin={{ top: 'xsmall' }}>
                {Object.values(catMeta).map(c => {
                const active = !focusedId || focusedId === c.id
                return (
                    <Box
                    key={c.id}
                    direction="row"
                    gap="xxsmall"
                    align="center"
                    pad={{ horizontal: 'xxsmall', vertical: 'xxsmall' }}
                    round="xsmall"
                    border={{ color: active ? 'border' : 'background', size: 'xsmall' }}
                    onClick={() => setFocusedId(focusedId === c.id ? null : c.id)}
                    style={{ cursor: 'pointer', opacity: active ? 1 : 0.35 }}
                    >
                    <span style={{
                        display: 'inline-block', width: 10, height: 10, borderRadius: 2,
                        background: c.color || '#999'
                    }} />
                    <Text size="xsmall">{c.emoji || '📁'} {c.name}</Text>
                    </Box>
                )
                })}
            </Box>
            </Box>
    </Box>
  )
}
