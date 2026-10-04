import { useEffect, useRef, useState } from "react";
import Modal from "./Modal";
import { Expand, LoaderCircle, ZoomIn, ZoomOut } from "lucide-react";

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
  const [zoom, setZoom] = useState(1);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const drag = useRef<{
    x: number;
    y: number;
    startX: number;
    startY: number;
  } | null>(null);
  useEffect(() => {
    setZoom(1);
    setPosition({ x: 0, y: 0 });
    drag.current = null;
  }, [imageId ?? source]);
  function changeZoom(value: number) {
    setZoom(Math.max(0.25, Math.min(8, value)));
  }
  function fit() {
    setZoom(1);
    setPosition({ x: 0, y: 0 });
  }
  return (
    <Modal
      title="이미지 보기"
      className="lightbox"
      onClose={onClose}
      onReturnFocus={onReturnFocus}
      toolbar={
        <div className="viewer-toolbar">
          {positionLabel && <span className="viewer-position" aria-live="polite">{positionLabel}</span>}
          <button
            className="icon-button"
            aria-label="화면 맞춤"
            title="화면 맞춤"
            onClick={fit}
          >
            <Expand size={18} aria-hidden="true" />
          </button>
          <button aria-label="축소" onClick={() => changeZoom(zoom / 1.25)}>
            <ZoomOut size={18} aria-hidden="true" />
          </button>
          <span>{Math.round(zoom * 100)}%</span>
          <button aria-label="확대" onClick={() => changeZoom(zoom * 1.25)}>
            <ZoomIn size={18} aria-hidden="true" />
          </button>
        </div>
      }
    >
      <div
        className="viewer"
        onWheel={(event) =>
          changeZoom(zoom * (event.deltaY < 0 ? 1.1 : 1 / 1.1))
        }
        onPointerDown={(event) => {
          drag.current = {
            x: event.clientX,
            y: event.clientY,
            startX: position.x,
            startY: position.y,
          };
          event.currentTarget.setPointerCapture?.(event.pointerId);
        }}
        onPointerMove={(event) => {
          if (drag.current)
            setPosition({
              x: drag.current.startX + event.clientX - drag.current.x,
              y: drag.current.startY + event.clientY - drag.current.y,
            });
        }}
        onPointerUp={() => {
          drag.current = null;
        }}
        onPointerCancel={() => {
          drag.current = null;
        }}
      >
        {source ? <img
          alt="생성 이미지 전체 화면"
          src={source}
          draggable={false}
          style={{
            transform: `translate(${position.x}px, ${position.y}px) scale(${zoom})`,
          }}
        /> : <LoaderCircle className="spinner" size={24} aria-label="이미지를 불러오는 중" />}
      </div>
    </Modal>
  );
}
