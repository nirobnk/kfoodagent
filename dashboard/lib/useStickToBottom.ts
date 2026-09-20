'use client';

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';

// How close to the live end still counts as "reading the latest". Below this
// the reader is deliberately back in the history and must not be dragged away
// from it.
const NEAR_BOTTOM_PX = 120;

// The first paint has to land at the bottom before the browser shows anything,
// or a long thread flashes its oldest message. useLayoutEffect does that; on
// the server it does not exist, and these pages are prerendered at build time.
const useIsoLayoutEffect = typeof window === 'undefined' ? useEffect : useLayoutEffect;

/**
 * Keeps a scrolling list pinned to its newest item the way a chat should.
 *
 * Three behaviours, and the naive version — scrollIntoView on every change —
 * gets all three wrong:
 *
 *   * Opening a thread lands on the newest message immediately. A smooth
 *     scroll here animates the whole history past the reader, which is the
 *     "it scrolls from the beginning" complaint.
 *   * A message arriving while you are at the bottom follows it down.
 *   * A message arriving while you are reading further up leaves the scroll
 *     exactly where it is and reports itself through `unseen` instead.
 *
 * Whether the reader was at the live end can only be answered *before* the new
 * item is added, because appending changes scrollHeight without firing a
 * scroll event. That is why it is tracked in a ref by the scroll handler
 * rather than measured when the effect runs.
 *
 * @param count     how many items are in the list
 * @param resetKey  changes when the list is a different conversation entirely
 */
export function useStickToBottom(count: number, resetKey: string) {
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const contentRef = useRef<HTMLDivElement | null>(null);

  const atLiveEndRef = useRef(true);
  const unpositionedRef = useRef(true);
  const [unseen, setUnseen] = useState(0);

  const jumpToEnd = useCallback((behavior: ScrollBehavior = 'smooth') => {
    const scroller = scrollerRef.current;
    if (!scroller) return;
    scroller.scrollTo({ top: scroller.scrollHeight, behavior });
    atLiveEndRef.current = true;
    setUnseen(0);
  }, []);

  const onScroll = useCallback(() => {
    const scroller = scrollerRef.current;
    if (!scroller) return;
    const distance = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;
    atLiveEndRef.current = distance <= NEAR_BOTTOM_PX;
    if (atLiveEndRef.current) setUnseen(0);
  }, []);

  // Declared before the effect below so a new conversation is marked
  // unpositioned before anything tries to place it.
  useEffect(() => {
    unpositionedRef.current = true;
    atLiveEndRef.current = true;
    setUnseen(0);
  }, [resetKey]);

  useIsoLayoutEffect(() => {
    if (count === 0) return;

    if (unpositionedRef.current) {
      unpositionedRef.current = false;
      jumpToEnd('auto');
      return;
    }

    if (atLiveEndRef.current) jumpToEnd('smooth');
    else setUnseen((seen) => seen + 1);
  }, [count, jumpToEnd]);

  // A photo finishes loading after its bubble has been measured, so the bottom
  // moves once more. Without this the newest message sits just under the fold
  // whenever the conversation ends in an image.
  useEffect(() => {
    const scroller = scrollerRef.current;
    const content = contentRef.current;
    if (!scroller || !content || typeof ResizeObserver === 'undefined') return;

    const observer = new ResizeObserver(() => {
      if (atLiveEndRef.current) scroller.scrollTop = scroller.scrollHeight;
    });
    observer.observe(content);
    return () => observer.disconnect();
  }, []);

  return { scrollerRef, contentRef, onScroll, unseen, jumpToEnd };
}
