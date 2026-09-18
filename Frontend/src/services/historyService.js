import { api } from './api';

/**
 * GET /history – full list of stored validation reports.
 * The backend currently returns all records at once (no pagination params),
 * so filtering/search is done client-side on the History page.
 */
export async function getHistory() {
  const data = await api.get('/history');
  if (!data || !Array.isArray(data.reports)) {
    return { reports: [], count: 0 };
  }
  return { reports: data.reports, count: data.count ?? data.reports.length };
}
