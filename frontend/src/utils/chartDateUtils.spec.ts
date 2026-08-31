import { describe, expect, it } from 'vitest'
import { buildDateLookup, dateToIdxRobust, normDateTime, resolveBarRange } from './chartDateUtils'

describe('chartDateUtils', () => {
  const dates = ['2024-01-02', '2024-01-03', '2024-01-04']

  it('dateToIdxRobust finds exact match', () => {
    expect(dateToIdxRobust('2024-01-03', dates)).toBe(1)
  })

  it('dateToIdxRobust uses lookup map', () => {
    const lookup = buildDateLookup(dates)
    expect(dateToIdxRobust('2024-01-04', dates, lookup)).toBe(2)
  })

  it('resolveBarRange maps valid endpoints to the visible bounds', () => {
    const r = resolveBarRange('2024-01-01', '2024-01-99', 3, dates)
    expect(r).toBeNull()
  })

  it('keeps intraday bars on the same day distinct', () => {
    const intraday = [
      '2024-01-03 09:30:00',
      '2024-01-03 09:35:00',
      '2024-01-03 09:40:00',
    ]
    const lookup = buildDateLookup(intraday)
    expect(dateToIdxRobust('2024-01-03T09:30:00', intraday, lookup)).toBe(0)
    expect(dateToIdxRobust('2024-01-03T09:35:00', intraday, lookup)).toBe(1)
    expect(dateToIdxRobust('2024-01-03T09:40:00', intraday, lookup)).toBe(2)
    expect(lookup.has('2024-01-03')).toBe(false)
  })

  it('normalizes minute timestamps without discarding time', () => {
    expect(normDateTime('2024-01-03T09:35')).toBe('2024-01-03 09:35:00')
  })
})
