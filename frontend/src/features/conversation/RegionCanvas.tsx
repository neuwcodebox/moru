import { forwardRef, useEffect, useImperativeHandle, useLayoutEffect, useRef, useState } from "react";
import type { CSSProperties, PointerEvent } from "react";
import { useTranslation } from "react-i18next";
import { Eraser, Expand, Paintbrush, Undo2 } from "lucide-react";
import { zoomAt } from "./imageViewport";
import type { ImageView } from "./imageViewport";

export type Stroke = { points: { x: number; y: number }[]; sizePx: number; erase: boolean };
export type MaskCanvas = { mask: () => string | null };
type Point = { x: number; y: number };

export function imagePoint(x: number, y: number, box: { left: number; top: number; width: number; height: number }) {
  return {
    x: Math.max(0, Math.min(1, (x - box.left) / box.width)),
    y: Math.max(0, Math.min(1, (y - box.top) / box.height)),
  };
}

const RegionCanvas = forwardRef<MaskCanvas, {
  source: string; width: number; height: number; strokes: Stroke[];
  onChange: (strokes: Stroke[]) => void; disabled: boolean;
}>(function RegionCanvas({ source, width, height, strokes, onChange, disabled }, ref) {
  const { t } = useTranslation("dialogs");
  const canvas = useRef<HTMLCanvasElement>(null);
  const viewport = useRef<HTMLDivElement>(null);
  const image = useRef<HTMLDivElement>(null);
  const pending = useRef<Stroke | null>(null);
  const pointer = useRef<number | null>(null);
  const pan = useRef<Point | null>(null);
  const maxSize = Math.max(100, Math.min(512, Math.max(width, height)));
  const [size, setSize] = useState(100);
  const [previewingSize, setPreviewingSize] = useState(false);
  const [erase, setErase] = useState(false);
  const [visible, setVisible] = useState(true);
  const [view, setView] = useState<ImageView>({ zoom: 1, x: 0, y: 0 });
  const [panning, setPanning] = useState(false);
  const [cursor, setCursor] = useState<Point | null>(null);

  useLayoutEffect(() => {
    if (!previewingSize) return;
    function centerPreview() {
      const frame = viewport.current!.getBoundingClientRect();
      const bounds = image.current!.getBoundingClientRect();
      if (!bounds.width || !bounds.height) return;
      // Do not clamp: the visible center can lie outside a panned image.
      setCursor({
        x: (frame.left + frame.width / 2 - bounds.left) / bounds.width,
        y: (frame.top + frame.height / 2 - bounds.top) / bounds.height,
      });
    }
    centerPreview();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(centerPreview);
    observer.observe(viewport.current!);
    return () => observer.disconnect();
  }, [previewingSize, view, width, height]);

  useEffect(() => {
    const element = viewport.current;
    if (!element) return;
    const wheel = (event: WheelEvent) => {
      event.preventDefault();
      event.stopPropagation();
      if (disabled || event.deltaY === 0) return;
      const bounds = element.getBoundingClientRect();
      setView((current) => zoomAt(current, event.deltaY < 0 ? 1.1 : 1 / 1.1, {
        x: event.clientX - bounds.left - bounds.width / 2,
        y: event.clientY - bounds.top - bounds.height / 2,
      }));
    };
    element.addEventListener("wheel", wheel, { passive: false });
    return () => element.removeEventListener("wheel", wheel);
  }, [disabled]);

  function render(items: Stroke[]) {
    const context = canvas.current?.getContext("2d");
    if (!context) return;
    context.clearRect(0, 0, width, height);
    for (const stroke of items) {
      context.globalCompositeOperation = stroke.erase ? "destination-out" : "source-over";
      context.strokeStyle = "#83b4f2";
      context.lineCap = "round";
      context.lineJoin = "round";
      context.lineWidth = stroke.sizePx;
      context.beginPath();
      stroke.points.forEach((p, index) => {
        if (index) context.lineTo(p.x * width, p.y * height);
        else context.moveTo(p.x * width, p.y * height);
      });
      if (stroke.points.length === 1) {
        const p = stroke.points[0];
        context.lineTo(p.x * width + .01, p.y * height + .01);
      }
      context.stroke();
    }
    context.globalCompositeOperation = "source-over";
  }

  useEffect(() => { render(strokes); }, [strokes, width, height]);
  useImperativeHandle(ref, () => ({ mask: () => {
    const element = canvas.current;
    const context = element?.getContext("2d");
    if (!element || !context) return null;
    const mask = context.getImageData(0, 0, width, height);
    let selected = false;
    for (let i = 0; i < mask.data.length; i += 4) {
      const value = mask.data[i + 3] >= 128 ? 255 : 0;
      selected ||= value === 255;
      mask.data[i] = mask.data[i + 1] = mask.data[i + 2] = value;
      mask.data[i + 3] = 255;
    }
    if (!selected) return null;
    const output = document.createElement("canvas");
    output.width = width; output.height = height;
    const outputContext = output.getContext("2d");
    if (!outputContext) return null;
    outputContext.putImageData(mask, 0, 0);
    return output.toDataURL("image/png");
  } }), [width, height]);

  function point(event: PointerEvent<HTMLDivElement>) {
    return imagePoint(event.clientX, event.clientY, image.current!.getBoundingClientRect());
  }
  function showCursor(event: PointerEvent<HTMLDivElement>) {
    setPreviewingSize(false);
    const bounds = image.current!.getBoundingClientRect();
    const inside = event.clientX >= bounds.left && event.clientX <= bounds.right &&
      event.clientY >= bounds.top && event.clientY <= bounds.bottom;
    setCursor(!disabled && inside ? point(event) : null);
  }
  function finish() {
    if (pending.current) {
      const stroke = pending.current;
      pending.current = null;
      onChange([...strokes, stroke]);
    }
    pointer.current = null;
    pan.current = null;
    setPanning(false);
  }
  function fit() {
    finish();
    setPreviewingSize(false);
    setView({ zoom: 1, x: 0, y: 0 });
    setCursor(null);
  }

  return <div className="region-paint">
    <fieldset disabled={disabled} className="region-tools">
      <button type="button" aria-label={t("region.brush")} title={t("region.brush")} aria-pressed={!erase}
        onClick={() => setErase(false)}><Paintbrush size={17} aria-hidden="true" /></button>
      <button type="button" aria-label={t("region.eraser")} title={t("region.eraser")} aria-pressed={erase}
        onClick={() => setErase(true)}><Eraser size={17} aria-hidden="true" /></button>
      <button type="button" aria-label={t("region.undo")} title={t("region.undo")} disabled={!strokes.length}
        onClick={() => onChange(strokes.slice(0, -1))}><Undo2 size={17} aria-hidden="true" /></button>
      <button type="button" disabled={!strokes.length} onClick={() => onChange([])}>{t("region.clear")}</button>
      <label className="region-brush-size">
        <span className="sr-only">{t("region.brushSize")}</span>
        <input type="range" min="1" max={maxSize} value={size}
          onFocus={() => setPreviewingSize(true)}
          onPointerDown={() => setPreviewingSize(true)}
          onBlur={() => { setPreviewingSize(false); setCursor(null); }}
          onChange={(event) => { setSize(Number(event.target.value)); setPreviewingSize(true); }} />
        <output>{size}px</output>
      </label>
      <button type="button" aria-label={t("lightbox.fit")} title={t("lightbox.fit")} onClick={fit}>
        <Expand size={17} aria-hidden="true" />
      </button>
      <label className="region-show-mask">
        <input type="checkbox" checked={visible} onChange={(event) => setVisible(event.target.checked)} />
        {t("region.showMask")}
      </label>
    </fieldset>
    <div className={`region-viewport${panning ? " is-panning" : ""}`} ref={viewport}
      onAuxClick={(event) => { if (event.button === 1) event.preventDefault(); }}
      onPointerDown={(event) => {
        if (disabled || pointer.current !== null) return;
        setPreviewingSize(false);
        if (event.button === 1) {
          pan.current = { x: event.clientX, y: event.clientY };
          setPanning(true);
          setCursor(null);
        } else if (event.button === 0 && event.target === canvas.current) {
          setVisible(true);
          pending.current = { points: [point(event)], sizePx: size, erase };
          render([...strokes, pending.current]);
          showCursor(event);
        } else return;
        event.preventDefault();
        pointer.current = event.pointerId;
        event.currentTarget.setPointerCapture?.(event.pointerId);
      }}
      onPointerMove={(event) => {
        if (pointer.current !== null && pointer.current !== event.pointerId) return;
        if (pan.current) {
          const dx = event.clientX - pan.current.x;
          const dy = event.clientY - pan.current.y;
          pan.current = { x: event.clientX, y: event.clientY };
          setView((current) => ({ ...current, x: current.x + dx, y: current.y + dy }));
          return;
        }
        showCursor(event);
        if (pending.current) {
          pending.current.points.push(point(event));
          render([...strokes, pending.current]);
        }
      }}
      onPointerUp={(event) => {
        if (pointer.current !== event.pointerId) return;
        finish();
        showCursor(event);
      }}
      onPointerCancel={finish}
      onLostPointerCapture={finish}
      onPointerLeave={() => setCursor(null)}>
      <div className="region-image" ref={image}
        style={{
          "--image-ratio": width / height,
          aspectRatio: `${width} / ${height}`,
          transform: `translate(${view.x}px, ${view.y}px) scale(${view.zoom})`,
        } as CSSProperties}>
        <img src={source} alt={t("region.original")} draggable={false} />
        <canvas ref={canvas} width={width} height={height} aria-label={t("region.selection")}
          style={{ opacity: visible ? .5 : 0, cursor: disabled ? "default" : "none" }} />
        {cursor && !disabled && !panning && <svg className="region-brush-cursor"
          viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
          <circle cx={cursor.x * width} cy={cursor.y * height} r={size / 2}
            fill="none" stroke="#000b" strokeWidth="3" strokeDasharray="4 3" vectorEffect="non-scaling-stroke" />
          <circle cx={cursor.x * width} cy={cursor.y * height} r={size / 2}
            fill="none" stroke="white" strokeWidth="1" strokeDasharray="4 3" vectorEffect="non-scaling-stroke" />
        </svg>}
      </div>
    </div>
  </div>;
});
export default RegionCanvas;
