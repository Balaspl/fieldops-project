/**
 * useActionState.ts
 * State machine hook for managing async action lifecycle:
 * IDLE → LOADING → SUCCESS | ERROR | TIMEOUT
 */
import { useState, useRef, useCallback, useEffect } from "react";
import type { ActionState, UseActionStateReturn } from "../types/notifications";

const TIMEOUT_MS = 30_000; // 30 seconds

export default function useActionState(): UseActionStateReturn {
  const [state, setState] = useState<ActionState>("IDLE");
  const [message, setMessage] = useState("");

  const lastActionRef = useRef<(() => Promise<void>) | null>(null);
  const timeoutIdRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      if (timeoutIdRef.current) clearTimeout(timeoutIdRef.current);
    };
  }, []);

  const clearTimeoutSafe = useCallback(() => {
    if (timeoutIdRef.current) {
      clearTimeout(timeoutIdRef.current);
      timeoutIdRef.current = null;
    }
  }, []);

  const execute = useCallback(
    async (actionFn: () => Promise<void>, label?: string) => {
      lastActionRef.current = actionFn;
      setState("LOADING");
      setMessage(label || "Processing your response…");

      // Start timeout timer
      timeoutIdRef.current = setTimeout(() => {
        if (mountedRef.current) {
          setState("TIMEOUT");
          setMessage("Taking longer than expected. You can retry or cancel.");
        }
      }, TIMEOUT_MS);

      try {
        await actionFn();
        clearTimeoutSafe();
        if (mountedRef.current) {
          setState("SUCCESS");
          setMessage(label ? `${label} — Done!` : "Done!");
        }
      } catch (err: any) {
        clearTimeoutSafe();
        if (mountedRef.current) {
          setState("ERROR");
          setMessage(err?.message || "Something went wrong. Please try again.");
        }
      }
    },
    [clearTimeoutSafe]
  );

  const retry = useCallback(() => {
    if (lastActionRef.current) {
      execute(lastActionRef.current);
    }
  }, [execute]);

  const reset = useCallback(() => {
    clearTimeoutSafe();
    setState("IDLE");
    setMessage("");
    lastActionRef.current = null;
  }, [clearTimeoutSafe]);

  return { state, message, execute, retry, reset };
}
