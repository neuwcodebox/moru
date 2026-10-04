import { useRef, useState } from "react";
import Modal from "./Modal";

export default function Lightbox({
  source,
  onClose,
}: {
  source: string;
  onClose: () => void;
}) {
  const [zoom, setZoom] = useState(1);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const drag = useRef<{
    x: number;
    y: number;
    startX: number;
    startY: number;
  } | null>(null);
  function changeZoom(value: number) {
    setZoom(Math.max(0.25, Math.min(8, value)));
  }
  function fit() {
    setZoom(1);
    setPosition({ x: 0, y: 0 });
  }
  return (
    <Modal title="이미지 보기" className="lightbox" onClose={onClose}>
      <div className="viewer-toolbar">
        <button onClick={fit}>화면 맞춤</button>
        <button aria-label="축소" onClick={() => changeZoom(zoom / 1.25)}>
          −
        </button>
        <span>{Math.round(zoom * 100)}%</span>
        <button aria-label="확대" onClick={() => changeZoom(zoom * 1.25)}>
          +
        </button>
      </div>
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
        <img
          alt="생성 이미지 전체 화면"
          src={source}
          draggable={false}
          style={{
            transform: `translate(${position.x}px, ${position.y}px) scale(${zoom})`,
          }}
        />
      </div>
    </Modal>
  );
}
