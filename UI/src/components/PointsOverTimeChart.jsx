import { useEffect, useState } from 'react'
import { Box, Button, Text } from 'grommet'
import {
  ResponsiveContainer, ComposedChart, Line, Area,
  XAxis, YAxis, Tooltip, CartesianGrid
} from 'recharts'
import API from '../api'
import { adaptTotalSeries } from '../lib/chartAdapters'
import { localISODate } from '../lib/date'
import { chartDims } from '../lib/ui'

const fmtDay = (iso) => (iso?.length >= 10 ? iso.slice(5) : iso)


export default function PointsOverTimeChart({ height }) {
  const [period, setPeriod] = useState('week')
  const [anchor] = useState(localISODate())
  const [data, setData] = useState([])
  const dims = chartDims()
  const H = height ?? dims.hLine

  useEffect(() => {
    let alive = true
    API.getPointsOverTime(period, anchor)
      .then(res => alive && setData(adaptTotalSeries(res)))
      .catch(() => alive && setData([]))
    return () => { alive = false }
  }, [period, anchor])

  return (
    <Box gap="xsmall">
      <Box direction="row" justify="between" align="center" margin={{ bottom: 'xsmall' }}>
        <Text weight="bold">Points over time</Text>
        <Box direction="row" gap="xxsmall">
          <Button size="small" primary={period==='week'} label="Week" onClick={() => setPeriod('week')} />
          <Button size="small" primary={period==='month'} label="Month" onClick={() => setPeriod('month')} />
        </Box>
      </Box>

      {/* Match page bg; set color so SVG can use 'currentColor' */}
      <Box
        height={`${H}px`}
        background="background"
        round="small"
        pad="xsmall"
        style={{ color: 'var(--grommet-text-color)' }}
      >
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={dims.margin}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="date" tick={{ fontSize: dims.tick }} tickFormatter={fmtDay}/>
            <YAxis tick={{ fontSize: dims.tick }} width={dims.yLeftPad} />
            <Tooltip formatter={(v) => [`${v} pts`, 'Total']} />
            {/* soft fill for visibility */}
            <Area type="monotone" dataKey="value" fill="currentColor" fillOpacity={0.15} stroke="none" />
            {/* crisp line on top */}
            <Line type="monotone" dataKey="value" stroke="currentColor" strokeWidth={2} dot={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </Box>
    </Box>
  )
}
