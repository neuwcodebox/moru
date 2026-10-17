import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { useState } from "react";
import RegionCanvas from "./RegionCanvas";
import type { Stroke } from "./regionMask";

let context: Partial<CanvasRenderingContext2D>;

beforeEach(() => {
  context = { lineWidth: 0, clearRect: vi.fn(), stroke: vi.fn(),
    beginPath: vi.fn(), moveTo: vi.fn(), lineTo: vi.fn() };
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context as never);
});

function box(left: number, top: number, width: number, height: number): DOMRect {
  return { left, top, width, height, right: left + width, bottom: top + height,
    x: left, y: top, toJSON: () => ({}) };
}

function editor(disabled = false) {
  const changed = vi.fn();
  function Editor() {
    const [strokes, setStrokes] = useState<Stroke[]>([]);
    return <RegionCanvas source="image" width={800} height={1200} strokes={strokes} disabled={disabled}
      onChange={(next) => { changed(next); setStrokes(next); }} />;
  }
  render(<Editor />);
  const canvas = screen.getByLabelText("수정할 영역 칠하기");
  const image = canvas.parentElement!;
  const viewport = image.parentElement!;
  vi.spyOn(viewport, "getBoundingClientRect").mockReturnValue(box(100, 60, 800, 600));
  const imageBox = vi.spyOn(image, "getBoundingClientRect").mockReturnValue(box(300, 60, 400, 600));
  return { canvas, image, viewport, imageBox, changed };
}

function pointer(target: HTMLElement, type: string, x: number, y: number, button = 0) {
  fireEvent(target, new MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y, button }));
}

function transform(image: HTMLElement, x: number, y: number, zoom: number) {
  const values = image.style.transform.match(/translate\(([^,]+)px, ([^)]+)px\) scale\(([^)]+)\)/)!;
  expect(Number(values[1])).toBeCloseTo(x);
  expect(Number(values[2])).toBeCloseTo(y);
  expect(Number(values[3])).toBeCloseTo(zoom);
}

it("uses original image pixels for both the brush stroke and cursor diameter", () => {
  const { canvas, image, changed } = editor();
  fireEvent.change(screen.getByRole("slider", { name: /붓 크기/ }), { target: { value: "80" } });
  expect(screen.getByText("80px")).toBeTruthy();
  pointer(canvas, "pointermove", 400, 210);
  const ring = image.querySelector("circle")!;
  expect(ring.getAttribute("r")).toBe("40");
  expect(ring.getAttribute("stroke-dasharray")).toBe("4 3");
  expect(ring.getAttribute("vector-effect")).toBe("non-scaling-stroke");
  expect(ring.getAttribute("cx")).toBe("200");
  expect(ring.getAttribute("cy")).toBe("300");
  pointer(canvas, "pointerdown", 400, 210);
  pointer(canvas, "pointerup", 400, 210);
  expect(context.lineWidth).toBe(80);
  expect(changed).toHaveBeenCalledExactlyOnceWith([
    { points: [{ x: .25, y: .25 }], sizePx: 80, erase: false },
  ]);
});

it("zooms around the cursor with consecutive wheel events and blocks native scrolling", () => {
  const { viewport, image, changed } = editor();
  const wheel = new WheelEvent("wheel", { clientX: 600, clientY: 210, deltaY: -100, cancelable: true });
  act(() => {
    viewport.dispatchEvent(wheel);
    viewport.dispatchEvent(new WheelEvent("wheel", { clientX: 600, clientY: 210, deltaY: -100 }));
  });
  expect(wheel.defaultPrevented).toBe(true);
  transform(image, -21, 31.5, 1.21);
  expect(changed).not.toHaveBeenCalled();
});

it("pans with the middle button over empty viewport space without painting", () => {
  const { viewport, image, changed } = editor();
  pointer(viewport, "pointerdown", 200, 200, 1);
  pointer(viewport, "pointermove", 240, 170, 1);
  pointer(viewport, "pointerup", 240, 170, 1);
  transform(image, 40, -30, 1);
  expect(changed).not.toHaveBeenCalled();
  expect(fireEvent(viewport, new MouseEvent("auxclick", { bubbles: true, button: 1, cancelable: true }))).toBe(false);
});

it("paints at the transformed image coordinates after zooming and panning", () => {
  const { canvas, viewport, imageBox, changed } = editor();
  fireEvent.wheel(viewport, { clientX: 600, clientY: 210, deltaY: -100 });
  pointer(viewport, "pointerdown", 200, 200, 1);
  pointer(viewport, "pointermove", 240, 180, 1);
  pointer(viewport, "pointerup", 240, 180, 1);
  imageBox.mockReturnValue(box(310, 25, 440, 660));
  pointer(canvas, "pointerdown", 420, 190);
  pointer(canvas, "pointerup", 420, 190);
  expect(changed).toHaveBeenCalledExactlyOnceWith([
    { points: [{ x: .25, y: .25 }], sizePx: 100, erase: false },
  ]);
  expect(context.lineWidth).toBe(100);
});

it("starts at 100px even when the image itself is smaller", () => {
  render(<RegionCanvas source="image" width={64} height={64} strokes={[]} disabled={false} onChange={vi.fn()} />);
  expect((screen.getByRole("slider", { name: /붓 크기/ }) as HTMLInputElement).value).toBe("100");
  expect(screen.getByText("100px")).toBeTruthy();
});

it("previews size changes live at the visible center without painting", () => {
  const { canvas, image, changed } = editor();
  const slider = screen.getByRole("slider", { name: /붓 크기/ });
  fireEvent.focus(slider);
  const ring = image.querySelector("circle")!;
  expect(ring.getAttribute("cx")).toBe("400");
  expect(ring.getAttribute("cy")).toBe("600");
  expect(ring.getAttribute("r")).toBe("50");
  fireEvent.change(slider, { target: { value: "160" } });
  expect(ring.getAttribute("r")).toBe("80");
  fireEvent.change(slider, { target: { value: "200" } });
  expect(ring.getAttribute("r")).toBe("100");
  expect(changed).not.toHaveBeenCalled();
  expect(context.stroke).not.toHaveBeenCalled();
  pointer(canvas, "pointermove", 400, 210);
  expect(ring.getAttribute("cx")).toBe("200");
  expect(ring.getAttribute("cy")).toBe("300");
  fireEvent.focus(slider);
  fireEvent.blur(slider);
  expect(image.querySelector("svg")).toBeNull();
});

it("keeps the size preview at the viewport center after the image is zoomed or panned aside", () => {
  const { image, imageBox, changed } = editor();
  imageBox.mockReturnValue(box(800, -100, 800, 1200));
  fireEvent.focus(screen.getByRole("slider", { name: /붓 크기/ }));
  const ring = image.querySelector("circle")!;
  expect(Number(ring.getAttribute("cx"))).toBeCloseTo(-300);
  expect(Number(ring.getAttribute("cy"))).toBeCloseTo(460);
  expect(changed).not.toHaveBeenCalled();
});

it("keeps the cursor out of the mask while hiding it during a pan and after leaving", () => {
  const { canvas, viewport, image } = editor();
  pointer(canvas, "pointermove", 400, 210);
  expect(image.querySelector("svg[aria-hidden=true]")).toBeTruthy();
  pointer(canvas, "pointerdown", 400, 210, 1);
  expect(image.querySelector("svg")).toBeNull();
  pointer(viewport, "pointerup", 400, 210, 1);
  expect(image.querySelector("svg")).toBeTruthy();
  fireEvent.pointerLeave(viewport);
  expect(image.querySelector("svg")).toBeNull();
  expect(context.stroke).not.toHaveBeenCalled();
});

it("fits the image again without changing the painted selection", () => {
  const { canvas, viewport, image, changed } = editor();
  pointer(canvas, "pointerdown", 400, 210);
  pointer(canvas, "pointerup", 400, 210);
  changed.mockClear();
  fireEvent.wheel(viewport, { clientX: 600, clientY: 210, deltaY: -100 });
  pointer(viewport, "pointerdown", 200, 200, 1);
  pointer(viewport, "pointermove", 250, 200, 1);
  fireEvent.click(screen.getByRole("button", { name: "화면 맞춤" }));
  pointer(viewport, "pointermove", 300, 200, 1);
  transform(image, 0, 0, 1);
  expect(changed).not.toHaveBeenCalled();
});

it("prevents navigation and painting while generation is being admitted", () => {
  const { canvas, viewport, image, changed } = editor(true);
  fireEvent.wheel(viewport, { clientX: 600, clientY: 210, deltaY: -100 });
  pointer(canvas, "pointerdown", 400, 210);
  pointer(viewport, "pointerdown", 200, 200, 1);
  pointer(viewport, "pointermove", 250, 200, 1);
  pointer(viewport, "pointerup", 250, 200, 1);
  transform(image, 0, 0, 1);
  expect(changed).not.toHaveBeenCalled();
  expect(image.querySelector("svg")).toBeNull();
});
