export type ImageView = { zoom: number; x: number; y: number };

export function imagePoint(x: number, y: number, box: { left: number; top: number; width: number; height: number }) {
  return {
    x: Math.max(0, Math.min(1, (x - box.left) / box.width)),
    y: Math.max(0, Math.min(1, (y - box.top) / box.height)),
  };
}

export function zoomAt(view: ImageView, factor: number, anchor = { x: 0, y: 0 }): ImageView {
  const zoom = Math.max(0.25, Math.min(8, view.zoom * factor));
  if (zoom === view.zoom) return view;
  const ratio = zoom / view.zoom;
  // Keep the same image point beneath the anchor, measured from the viewport center.
  return {
    zoom,
    x: anchor.x + (view.x - anchor.x) * ratio,
    y: anchor.y + (view.y - anchor.y) * ratio,
  };
}
