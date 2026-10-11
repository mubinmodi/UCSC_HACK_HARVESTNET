import { useCallback, useEffect, useRef, useState } from 'react';
import { describeError } from './api';

/** Load one API response, with loading and error state and a reload. */
export function useLoad<T>(load: (() => Promise<T>) | null, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const run = useRef(0);

  const reload = useCallback(async () => {
    if (!load) return;
    const id = ++run.current;
    setLoading(true);
    setError(null);
    try {
      const result = await load();
      if (id === run.current) setData(result);
    } catch (err) {
      if (id === run.current) {
        setData(null);
        setError(describeError(err));
      }
    } finally {
      if (id === run.current) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { data, error, loading, reload };
}

/** Run one write action at a time, keeping its error message. */
export function useAction() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const perform = useCallback(async <T,>(action: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true);
    setError(null);
    try {
      return await action();
    } catch (err) {
      setError(describeError(err));
      return undefined;
    } finally {
      setBusy(false);
    }
  }, []);
  return { busy, error, setError, perform };
}
