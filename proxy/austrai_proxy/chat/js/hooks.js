/**
 * AUSTR.AI — Custom Preact hooks bridging the global signal store and
 * Preact's component lifecycle.
 *
 * `useSignalValue(signal)` subscribes the calling component to a signal
 * and triggers a re-render whenever the signal changes. We avoid
 * Preact-Signals' implicit "read-from-JSX" magic because much of the
 * code path uses signal values inside plain JS (filters, conditionals)
 * before hitting JSX, where the implicit subscription would not fire.
 */

import { useState, useEffect } from 'preact/hooks';

export function useSignalValue(signal) {
  const [, force] = useState(0);
  useEffect(() => {
    if (!signal || typeof signal.subscribe !== 'function') return undefined;
    let first = true;
    return signal.subscribe(() => {
      // signal.subscribe replays the current value immediately on
      // subscribe — skip that to avoid an extra render on mount.
      if (first) { first = false; return; }
      force((n) => n + 1);
    });
  }, [signal]);
  return signal ? signal.value : undefined;
}
