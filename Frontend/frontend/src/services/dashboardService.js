import { api } from './api';

/**
 * GET /dashboard – aggregate statistics computed by the backend from the
 * validation_reports collection. The frontend never invents these numbers.
 */
export async function getDashboard() {
  const data = await api.get('/dashboard');
  if (!data || typeof data !== 'object') {
    return null;
  }
  return data;
}


