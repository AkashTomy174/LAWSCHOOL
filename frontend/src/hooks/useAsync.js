import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Minimal async-data hook.
 *
 * Why not a data library: the app has ~12 endpoints and no cache-coherency
 * requirements beyond "refetch after I mutate".  A focused hook keeps the
 * dependency surface small and the behaviour obvious.
 *
 * Guarantees provided:
 * * `loading` is only true for the first load (`isRefetching` for later ones), so
 *   a refresh does not blank out the page;
 * * results from a superseded request are discarded, so a fast retry cannot
 *   overwrite fresher data with a stale response;
 * * state is not set after unmount.
 *
 * @param {Function} fetcher Async function returning the data.
 * @param {Array} deps Dependency list; the fetcher runs again when these change.
 */
export function useAsync(
  fetcher,
  deps = [],
  { immediate = true, initialData = null } = {},
) {
  const [data, setData] = useState(initialData);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(immediate);
  const [isRefetching, setIsRefetching] = useState(false);

  // Monotonic request id: only the newest request may commit its result.
  const requestId = useRef(0);
  const mounted = useRef(true);
  const fetcherRef = useRef(fetcher);

  useEffect(() => {
    fetcherRef.current = fetcher;
  }, [fetcher]);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const run = useCallback(async ({ silent = false } = {}) => {
    const id = ++requestId.current;
    if (silent) setIsRefetching(true);
    else setLoading(true);
    setError(null);

    try {
      const result = await fetcherRef.current();
      if (!mounted.current || id !== requestId.current) return null;
      setData(result);
      return result;
    } catch (caught) {
      if (!mounted.current || id !== requestId.current) return null;
      setError(caught);
      return null;
    } finally {
      if (mounted.current && id === requestId.current) {
        setLoading(false);
        setIsRefetching(false);
      }
    }
  }, []);

  useEffect(() => {
    if (immediate) run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return {
    data,
    error,
    loading,
    isRefetching,
    /** Re-run the request. `silent` keeps the existing UI (no skeleton flash). */
    refetch: run,
    setData,
  };
}

export default useAsync;
