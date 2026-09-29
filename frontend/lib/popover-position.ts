/** Viewport coordinates, independent of overflow/blur on the writing workspace. */
export function positionPopover(anchor: { left: number; top: number; bottom: number }, panelWidth: number,
  viewport: { left: number; top: number; width: number; height: number }) {
  const gutter = 12;
  const gap = 8;
  const width = Math.max(0, Math.min(384, panelWidth - 24, viewport.width - gutter * 2));
  const left = Math.max(viewport.left + gutter, Math.min(anchor.left, viewport.left + viewport.width - gutter - width));
  const bottomEdge = viewport.top + viewport.height - gutter;
  const below = bottomEdge - anchor.bottom - gap;
  const above = anchor.top - gap - viewport.top - gutter;
  const goesAbove = below < 240 && above > below;
  const maxHeight = Math.max(0, Math.min(480, goesAbove ? above : below));
  const top = goesAbove ? anchor.top - gap - maxHeight : Math.max(viewport.top + gutter, anchor.bottom + gap);
  return { left, top, width, maxHeight };
}
