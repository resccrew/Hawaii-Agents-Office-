"use client";

import { useEffect, useRef } from "react";

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Accessible-modal behavior shared by AddAgentButton's spawn form and
 * SettingsModal (the pattern GitBar.tsx already had for its own inline
 * "connect" form's Escape-to-cancel, just generalized and made reusable):
 * - focuses the first focusable element inside the dialog on mount
 * - traps Tab/Shift+Tab so focus can't leave the dialog into the page
 *   behind it (e.g. the scrolling activity log)
 * - Escape calls `onClose`
 * - on unmount, returns focus to whatever element had it before the dialog
 *   opened (typically the button that triggered it)
 *
 * Attach the returned ref to the dialog's outermost element (the one with
 * role="dialog"/aria-modal="true").
 */
export function useFocusTrap<T extends HTMLElement>(onClose: () => void) {
  const containerRef = useRef<T | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const previouslyFocused = document.activeElement as HTMLElement | null;

    const focusables = () =>
      Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
        (el) => el.offsetParent !== null || el === document.activeElement,
      );

    const first = focusables()[0];
    (first ?? container).focus();

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
        return;
      }
      if (e.key !== "Tab") return;
      const items = focusables();
      if (items.length === 0) return;
      const currentIndex = items.indexOf(document.activeElement as HTMLElement);
      if (e.shiftKey) {
        if (currentIndex <= 0) {
          e.preventDefault();
          items[items.length - 1].focus();
        }
      } else {
        if (currentIndex === items.length - 1 || currentIndex === -1) {
          e.preventDefault();
          items[0].focus();
        }
      }
    };

    container.addEventListener("keydown", handleKeyDown);
    return () => {
      container.removeEventListener("keydown", handleKeyDown);
      // Return focus to whatever opened the dialog — but only if it's still
      // attached (it can't be if the whole view re-rendered underneath us).
      if (previouslyFocused && document.contains(previouslyFocused)) {
        previouslyFocused.focus();
      }
    };
    // Deliberately run once per mount — the dialog is mounted/unmounted by
    // its parent's conditional render, which is exactly the open/close
    // transition this hook cares about.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return containerRef;
}
