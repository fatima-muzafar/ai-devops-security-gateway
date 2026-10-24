// Loads one panel's data (decisions.md #103, #104).
// "loading" and "refreshing" are DERIVED from keys, so no state is set inside the effect body.
import { useEffect, useState } from "react";
import { ApiError } from "./api";

interface Result<T> {
  data: T | null;
  error: string | null;
  doneKey: string | null;
  scope: string | null;
}

export function usePanelData<T>(
  load: (token: string) => Promise<T>,
  token: string,
  externalKey: number,
  onUnauthorized: () => void,
  scope = "",
) {
  const [nonce, setNonce] = useState(0);
  const [result, setResult] = useState<Result<T>>({
    data: null,
    error: null,
    doneKey: null,
    scope: null,
  });
  const key = `${externalKey}:${nonce}:${scope}`;

  useEffect(() => {
    let cancelled = false;
    load(token).then(
      (data) => {
        if (!cancelled) setResult({ data, error: null, doneKey: key, scope });
      },
      (err: unknown) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) {
          onUnauthorized();
          return;
        }
        const message = err instanceof Error ? err.message : "Unknown error.";
        setResult((prev) => ({
          data: prev.scope === scope ? prev.data : null,
          error: message,
          doneKey: key,
          scope,
        }));
      },
    );
    return () => {
      cancelled = true;
    };
  }, [load, token, key, scope, onUnauthorized]);

  const fresh = result.scope === scope;
  const data = fresh ? result.data : null;
  const error = fresh ? result.error : null;
  return {
    data,
    error,
    loading: data === null && error === null,
    refreshing: result.doneKey !== key,
    reload: () => setNonce((n) => n + 1),
  };
}
