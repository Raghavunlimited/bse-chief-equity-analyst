/**
 * ISO week label matching Python ``date.isocalendar()`` → ``YYYY-Www``.
 * Uses the local calendar date (not UTC clock skew across midnight).
 */
export function isoWeekLabel(date = new Date()) {
  const y = date.getFullYear();
  const m = date.getMonth();
  const day = date.getDate();
  // Noon UTC on the local Y-M-D avoids DST / timezone edge cases.
  const utc = new Date(Date.UTC(y, m, day, 12, 0, 0));
  // ISO weekday: Mon=1 … Sun=7
  const isoDow = utc.getUTCDay() || 7;
  // Thursday of this ISO week determines the week-year
  utc.setUTCDate(utc.getUTCDate() + 4 - isoDow);
  const isoYear = utc.getUTCFullYear();
  const jan4 = new Date(Date.UTC(isoYear, 0, 4, 12, 0, 0));
  const jan4Dow = jan4.getUTCDay() || 7;
  const week1Monday = new Date(jan4);
  week1Monday.setUTCDate(jan4.getUTCDate() - (jan4Dow - 1));
  const weekNo =
    1 + Math.round((utc.getTime() - week1Monday.getTime()) / 604800000);
  return `${isoYear}-W${String(weekNo).padStart(2, '0')}`;
}
