import { useState, useCallback } from "react";

/**
 * Generic undo/redo hook with a history limit of 50 entries.
 * Keeps track of past states, current state, and future states.
 */
export function useUndoRedo<T>(initialState: T) {
  const [past, setPast] = useState<T[]>([]);
  const [present, setPresent] = useState<T>(initialState);
  const [future, setFuture] = useState<T[]>([]);

  const MAX_HISTORY = 50;

  const set = useCallback(
    (newState: T) => {
      setPast((p) => {
        const updated = [...p, present];
        return updated.length > MAX_HISTORY ? updated.slice(-MAX_HISTORY) : updated;
      });
      setPresent(newState);
      setFuture([]);
    },
    [present]
  );

  const undo = useCallback(() => {
    if (past.length === 0) return;
    setFuture((f) => [present, ...f]);
    setPresent(past[past.length - 1]);
    setPast((p) => p.slice(0, -1));
  }, [past, present]);

  const redo = useCallback(() => {
    if (future.length === 0) return;
    setPast((p) => [...p, present]);
    setPresent(future[0]);
    setFuture((f) => f.slice(1));
  }, [future, present]);

  const reset = useCallback((s: T) => {
    setPast([]);
    setPresent(s);
    setFuture([]);
  }, []);

  return {
    state: present,
    set,
    undo,
    redo,
    canUndo: past.length > 0,
    canRedo: future.length > 0,
    reset,
  };
}
