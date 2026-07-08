import { useEffect, useRef, useCallback } from "react";

const BASE = import.meta.env.PROD ? "" : "";

export function useSSE({ onIssueUpdate, onStatsUpdate, onConnected }) {
  const ref = useRef(null);
  const retries = useRef(0);

  const connect = useCallback(() => {
    const es = new EventSource(`${BASE}/api/events`);
    ref.current = es;

    es.addEventListener("connected", () => {
      retries.current = 0;
      onConnected?.(true);
    });

    es.addEventListener("issue_update", (e) => {
      try {
        onIssueUpdate?.(JSON.parse(e.data));
      } catch {}
    });

    es.addEventListener("stats_update", (e) => {
      try {
        onStatsUpdate?.(JSON.parse(e.data));
      } catch {}
    });

    es.onerror = () => {
      es.close();
      onConnected?.(false);
      const delay = Math.min(1000 * 2 ** retries.current, 15000);
      retries.current++;
      setTimeout(connect, delay);
    };
  }, [onIssueUpdate, onStatsUpdate, onConnected]);

  useEffect(() => {
    connect();
    return () => ref.current?.close();
  }, [connect]);
}
