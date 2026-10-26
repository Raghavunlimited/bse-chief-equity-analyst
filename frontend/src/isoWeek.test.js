import { isoWeekLabel } from './isoWeek';

describe('isoWeekLabel', () => {
  it('matches Python isocalendar for 2026-10-26 (ISO week 44)', () => {
    // Local Y-M-D constructor — same as desk "today" in IST
    expect(isoWeekLabel(new Date(2026, 9, 26))).toBe('2026-W44');
  });

  it('labels Friday 2026-10-23 as week 43', () => {
    expect(isoWeekLabel(new Date(2026, 9, 23))).toBe('2026-W43');
  });

  it('handles ISO week-year near Jan boundary', () => {
    // 2026-01-01 is Thursday → still ISO week 1 of 2026
    expect(isoWeekLabel(new Date(2026, 0, 1))).toBe('2026-W01');
    // 2025-12-29 is Monday of 2026-W01
    expect(isoWeekLabel(new Date(2025, 11, 29))).toBe('2026-W01');
  });
});
