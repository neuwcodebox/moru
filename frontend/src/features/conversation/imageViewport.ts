export type ImageView = { zoom: number; x: number; y: number };

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
