"use client";

import { useLayoutEffect, useRef, type ReactNode, type RefObject } from "react";
import { createPortal } from "react-dom";
import { positionPopover } from "@/lib/popover-position";

export default function AnchoredPopover({ open, onClose, anchorRef, boundaryRef, id, label, theme, children }: {
  open: boolean;
  onClose: () => void;
  anchorRef: RefObject<HTMLElement | null>;
  boundaryRef: RefObject<HTMLElement | null>;
  id: string;
  label: string;
  theme: string;
  children: ReactNode;
}) {
  const popupRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  useLayoutEffect(() => { closeRef.current = onClose; });
  useLayoutEffect(() => {
    const popup = popupRef.current;
    const anchor = anchorRef.current;
    const boundary = boundaryRef.current;
    if (!open || !popup || !anchor || !boundary) return;
    const reposition = () => {
      // Responsive layout may hide the whole sidebar. Do not leave an orphaned portal.
      const boundaryWidth = boundary.getBoundingClientRect().width;
      if (boundaryWidth < 1 || anchor.getClientRects().length === 0) {
        closeRef.current();
        return;
      }
      const vv = window.visualViewport;
      const placement = positionPopover(anchor.getBoundingClientRect(), boundaryWidth, {
        left: vv?.offsetLeft ?? 0, top: vv?.offsetTop ?? 0,
        width: vv?.width ?? window.innerWidth, height: vv?.height ?? window.innerHeight,
      });
      Object.assign(popup.style, Object.fromEntries(Object.entries(placement).map(([key, value]) => [key, `${value}px`])));
    };
    reposition();
    popup.querySelector<HTMLInputElement>("input")?.focus({ preventScroll: true });
    const observer = new ResizeObserver(reposition);
    observer.observe(boundary);
    observer.observe(anchor);
    const outside = (event: PointerEvent | FocusEvent) => {
      const target = event.target;
      if (target instanceof Node && !popup.contains(target) && !anchor.contains(target)) closeRef.current();
    };
    document.addEventListener("pointerdown", outside, true);
    document.addEventListener("focusin", outside);
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
    window.visualViewport?.addEventListener("resize", reposition);
    window.visualViewport?.addEventListener("scroll", reposition);
    return () => {
      observer.disconnect();
      document.removeEventListener("pointerdown", outside, true);
      document.removeEventListener("focusin", outside);
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
      window.visualViewport?.removeEventListener("resize", reposition);
      window.visualViewport?.removeEventListener("scroll", reposition);
      // Outside clicks keep their target's focus; closing from inside returns to the trigger.
      if (popup.contains(document.activeElement)) anchor.focus({ preventScroll: true });
    };
  }, [open, anchorRef, boundaryRef]);

  if (!open || typeof document === "undefined") return null;
  return createPortal(<div ref={popupRef} id={id} role="dialog" aria-label={label} data-theme={theme}
    className="novelcat-ai-panel novelcat-history-popover novelcat-chat-secondary"
    onKeyDown={event => {
      if (event.key === "Escape") {
        event.preventDefault(); event.stopPropagation();
        anchorRef.current?.focus({ preventScroll: true });
        onClose();
      }
    }}>{children}</div>, document.body);
}
