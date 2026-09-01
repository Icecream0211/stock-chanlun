import { describe, expect, it } from 'vitest'
import {
  buildDateLookup,
  dateToIdxRobust,
  formatAdaptiveTimeAxisLabel,
  normDateTime,
  percentToVisibleIndexRange,
  resolveAdaptiveTimeAxisMode,
  resolveBarRange,
} from './chartDateUtils'

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

  it('switches time-axis granularity with the visible range', () => {
    const longRange = ['2022-01-01', '2023-06-01', '2024-06-01']
    expect(resolveAdaptiveTimeAxisMode(longRange)).toBe('year')
    expect(resolveAdaptiveTimeAxisMode(['2024-01-01', '2024-05-01'])).toBe('month')
    expect(resolveAdaptiveTimeAxisMode(['2024-01-01', '2024-01-10'])).toBe('day')
    expect(resolveAdaptiveTimeAxisMode([
      '2024-01-03 09:30:00',
      '2024-01-03 10:00:00',
    ])).toBe('time')
  })

  it('formats only year/month boundaries and keeps intraday time', () => {
    const yearly = ['2023-12-29', '2024-01-02', '2024-12-31', '2025-01-02']
    expect(formatAdaptiveTimeAxisLabel(yearly[0], 0, yearly)).toBe('2023')
    expect(formatAdaptiveTimeAxisLabel(yearly[2], 2, yearly)).toBe('')
    expect(formatAdaptiveTimeAxisLabel(yearly[3], 3, yearly)).toBe('2025')

    const intraday = ['2024-01-03 09:30:00', '2024-01-03 10:00:00']
    expect(formatAdaptiveTimeAxisLabel(intraday[0], 0, intraday)).toBe('01-03\n09:30')
    expect(formatAdaptiveTimeAxisLabel(intraday[1], 1, intraday)).toBe('10:00')
  })

  it('uses the category value when ECharts supplies a zoom-local tick index', () => {
    const monthly = ['2024-01-01', '2024-03-01', '2024-03-02', '2024-06-01']
    expect(formatAdaptiveTimeAxisLabel(monthly[2], 0, monthly, 1, 3)).toBe('')
    expect(formatAdaptiveTimeAxisLabel(monthly[3], 1, monthly, 1, 3)).toBe('06月')
  })

  it('maps zoom percentages to bounded visible indices', () => {
    expect(percentToVisibleIndexRange(101, 70, 100)).toEqual([70, 100])
    expect(percentToVisibleIndexRange(10, -5, 120)).toEqual([0, 9])
  })
})
