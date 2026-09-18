import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../services/api.js';

/**
 * Small data-fetching hook: loading/error/result state with safe unmount
 * handling and a manual refetch. Errors are normalized to ApiError when
 * possible so pages can branch on error.kind.
 */
export function useAsync(asyncFn, { immediate = true } = {}) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(immediate);
  const aliveRef = useRef(true);
  const fnRef = useRef(asyncFn);
  fnRef.current = asyncFn;

  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);

  const run = useCallback(async (...args) => {
    setLoading(true);
    setError(null);
    try {
      const result = await fnRef.current(...args);
      if (aliveRef.current) setData(result);
      return result;
    } catch (err) {
      if (aliveRef.current) {
        setError(
          err instanceof ApiError
            ? err
            : new ApiError('unknown', err?.message || 'An unexpected error occurred.')
        );
      }
      return undefined;
    } finally {
      if (aliveRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (immediate) run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { data, error, loading, refetch: run };
}
