// src/components/UserSummaryCard.jsx
import React from 'react'
import { Box, Text } from 'grommet'

/**
 * summary: {
 *   id,
 *   username,
 *   emoji,
 *   accent_color,
 *   title,
 *   top_categories: [
 *     { category_id, name, emoji, color, points }
 *   ]
 * }
 */
export default function UserSummaryCard({ summary }) {
  if (!summary) return null

  const {
    username,
    emoji,
    accent_color,
    title,
    top_categories = [],
  } = summary

  const maxPoints = top_categories.reduce(
    (m, c) => (c.points > m ? c.points : m),
    0
  )

  const CHART_HEIGHT = 120 // px

  const hasData = top_categories.length > 0 && maxPoints > 0
  const midPoints = hasData ? Math.round(maxPoints / 2) : 0

  return (
    <Box
      border={{ color: accent_color || 'brand', size: 'small' }}
      pad="xsmall"
      round="medium"
      margin={{ vertical: 'xsmall' }}
      flex={false}
    >
      <Box
        background="background-front"
        pad="small"
        round="small"
        height="280px"
        gap="small"
      >
        {/* Header: avatar + username */}
        <Box direction="row" gap="small" align="center">
          <Box
            width="44px"
            height="44px"
            round="full"
            background={accent_color || 'brand'}
            align="center"
            justify="center"
          >
            <Text size="large">{emoji || '🙂'}</Text>
          </Box>
          <Text weight="bold" truncate>
            {username}
          </Text>
        </Box>

        {/* Chart + labels */}
        <Box flex={{ grow: 3 }} direction="column" gap="xxsmall">
          {!hasData ? (
            <Text size="small">No recent points yet.</Text>
          ) : (
            <>
              {/* CHART ROW: Y-axis + bars. Bottom of this row is 0-line. */}
              <Box direction="row" gap="xsmall">
                {/* Y-axis: explicitly top / middle / bottom */}
                <Box
                  width="40px"
                  height={`${CHART_HEIGHT}px`}
                  justify="between"
                  align="flex-end"
                  pad={{ right: 'xxsmall' }}
                >
                  <Text size="xsmall">{maxPoints}</Text>
                  <Text size="xsmall">{midPoints}</Text>
                  <Text size="xsmall">0</Text>
                </Box>

                {/* Bars: same fixed height, aligned to bottom */}
                <Box
                  direction="row"
                  gap="small"
                  flex={{ grow: 1 }}
                  height={`${CHART_HEIGHT}px`}
                  align="flex-end"
                >
                  {top_categories.map(cat => {
                    const pts = cat.points || 0
                    const rawHeight = (pts / maxPoints) * CHART_HEIGHT
                    const barHeight = Math.max(8, rawHeight)

                    return (
                      <Box
                        key={cat.category_id}
                        flex={{ grow: 1 }}
                        align="center"
                      >
                        <Box
                          height={`${barHeight}px`}
                          width="100%"
                          background={cat.color || 'brand'}
                          round="xsmall"
                        />
                      </Box>
                    )
                  })}
                </Box>
              </Box>

              {/* LABEL ROW: perfectly mirrors the bar layout */}
              <Box direction="row" gap="xsmall" margin={{ top: 'xxsmall' }}>
                {/* spacer under y-axis */}
                <Box width="40px" />
                <Box
                  direction="row"
                  gap="small"
                  flex={{ grow: 1 }}
                >
                  {top_categories.map(cat => {
                    const fullName = cat.name || ''
                    const labelName =
                      fullName.length > 8
                        ? `${fullName.slice(0, 7)}…`
                        : fullName

                    return (
                      <Box
                        key={cat.category_id}
                        flex={{ grow: 1 }}
                        align="center"
                      >
                        {/* emoji centered under bar */}
                        <Text size="small">{cat.emoji || '•'}</Text>
                        {/* aggressively truncated name */}
                        <Text
                          size="xsmall"
                          margin={{ top: 'xxsmall' }}
                          textAlign="center"
                          style={{
                            whiteSpace: 'nowrap',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                          }}
                        >
                          {labelName}
                        </Text>
                      </Box>
                    )
                  })}
                </Box>
              </Box>
            </>
          )}
        </Box>

        {/* Title card (bottom ~25%) */}
        <Box flex={{ grow: 1 }} justify="center">
          <Text
            size="large"
            weight="bold"
            textAlign="center"
            alignSelf="center"
            margin={{ top: 'small', bottom: 'small' }}
            style={{ lineHeight: 1.4 }}
            >
            🏅 {title} 🏅
            </Text>
        </Box>
      </Box>
    </Box>
  )
}
