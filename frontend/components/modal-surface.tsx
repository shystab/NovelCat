"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

/** Top-layer modal: independent of the workspace's blur and transform containers. */
export default function ModalSurface({ open, onClose, label, busy = false, wide = false, children }: {
  open: boolean;
  onClose: () => void;
  label: string;
  busy?: boolean;
  wide?: boolean;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!open || !dialog) return;
    const opener = document.activeElement;
    if (!dialog.open) dialog.showModal();
    return () => {
      if (dialog.open) dialog.close();
      if (opener instanceof HTMLElement && opener.isConnected) opener.focus({ preventScroll: true });
    };
  }, [open]);

  if (!open || typeof document === "undefined") return null;
  return createPortal(
    <dialog ref={ref} aria-label={label} aria-modal="true"
      onCancel={event => { event.preventDefault(); event.stopPropagation(); if (!busy) onClose(); }}
      onKeyDown={event => { if (event.key === "Escape") event.stopPropagation(); }}
      onClick={event => { if (event.target === event.currentTarget && !busy) {
        const bounds = event.currentTarget.getBoundingClientRect();
        if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) onClose();
      } }}
      className={`novelcat-modal-surface m-auto max-h-[90dvh] w-[calc(100%_-_2rem)] ${wide ? "max-w-xl" : "max-w-lg"} overflow-visible border-0 bg-transparent p-0`}>
      {children}
    </dialog>, document.body,
  );
}
