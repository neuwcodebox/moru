import { useTranslation } from "react-i18next";
import { useEffect, useRef, useState } from "react";
import Modal from "../../components/Modal";
import { Expand, LoaderCircle, ZoomIn, ZoomOut } from "lucide-react";

type ViewerTransform = { zoom: number; x: number; y: number };

function zoomAt(view: ViewerTransform, factor: number, anchor = { x: 0, y: 0 }): ViewerTransform {
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

export default function Lightbox({
  source,
  onClose,
  imageId,
  positionLabel,
  onReturnFocus,
}: {
  source: string | null;
  imageId?: string;
  positionLabel?: string;
  onClose: () => void;
  onReturnFocus?: () => void;
}) {
  const { t } = useTranslation("dialogs");
  const [view, setView] = useState<ViewerTransform>({ zoom: 1, x: 0, y: 0 });
  const drag = useRef<{
    x: number;
    y: number;
  } | null>(null);
  const viewer = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const element = viewer.current;
    if (!element) return;
    const wheel = (event: WheelEvent) => {
      event.preventDefault();
      event.stopPropagation();
      if (event.deltaY === 0) return;
      const bounds = element.getBoundingClientRect();
      const anchor = {
        x: event.clientX - bounds.left - bounds.width / 2,
        y: event.clientY - bounds.top - bounds.height / 2,
      };
      setView((current) => zoomAt(current, event.deltaY < 0 ? 1.1 : 1 / 1.1, anchor));
    };
    // React wheel listeners are passive; zoom must also cancel native scrolling.
    element.addEventListener("wheel", wheel, { passive: false });
    return () => element.removeEventListener("wheel", wheel);
  }, []);
  useEffect(() => {
    setView({ zoom: 1, x: 0, y: 0 });
    drag.current = null;
  }, [imageId ?? source]);
  function changeZoom(factor: number) {
    setView((current) => zoomAt(current, factor));
  }
  function fit() {
    setView({ zoom: 1, x: 0, y: 0 });
    drag.current = null;
  }
  return (
    <Modal
      title={t("lightbox.title")}
      className="lightbox"
      onClose={onClose}
      onReturnFocus={onReturnFocus}
      toolbar={
        <div className="viewer-toolbar">
          {positionLabel && <span className="viewer-position" aria-live="polite">{positionLabel}</span>}
          <button
            className="icon-button"
            aria-label={t("lightbox.fit")}
            title={t("lightbox.fit")}
            onClick={fit}
          >
            <Expand size={18} aria-hidden="true" />
          </button>
          <button aria-label={t("lightbox.zoomOut")} onClick={() => changeZoom(1 / 1.25)}>
            <ZoomOut size={18} aria-hidden="true" />
          </button>
          <span>{Math.round(view.zoom * 100)}%</span>
          <button aria-label={t("lightbox.zoomIn")} onClick={() => changeZoom(1.25)}>
            <ZoomIn size={18} aria-hidden="true" />
          </button>
        </div>
      }
    >
      <div
        className="viewer"
        ref={viewer}
        onPointerDown={(event) => {
          drag.current = {
            x: event.clientX,
            y: event.clientY,
          };
          event.currentTarget.setPointerCapture?.(event.pointerId);
        }}
        onPointerMove={(event) => {
          if (!drag.current) return;
          const dx = event.clientX - drag.current.x;
          const dy = event.clientY - drag.current.y;
          drag.current = { x: event.clientX, y: event.clientY };
          setView((current) => ({ ...current, x: current.x + dx, y: current.y + dy }));
        }}
        onPointerUp={() => {
          drag.current = null;
        }}
        onPointerCancel={() => {
          drag.current = null;
        }}
      >
        {source ? <img
          alt={t("lightbox.imageAlt")}
          src={source}
          draggable={false}
          style={{
            transform: `translate(${view.x}px, ${view.y}px) scale(${view.zoom})`,
          }}
        /> : <LoaderCircle className="spinner" size={24} aria-label={t("lightbox.loading")} />}
      </div>
    </Modal>
  );
}
