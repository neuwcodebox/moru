import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import Lightbox from "./Lightbox";

function openViewer() {
  render(<Lightbox source="data:image/png;base64,abc" onClose={vi.fn()} />);
  const image = screen.getByAltText("생성 이미지 전체 화면");
  const viewer = image.parentElement!;
  vi.spyOn(viewer, "getBoundingClientRect").mockReturnValue({
    left: 100, top: 60, width: 800, height: 600,
    right: 900, bottom: 660, x: 100, y: 60, toJSON: () => ({}),
  });
  return { image, viewer };
}

function expectTransform(image: HTMLElement, x: number, y: number, zoom: number) {
  const values = image.style.transform.match(/translate\(([^,]+)px, ([^)]+)px\) scale\(([^)]+)\)/);
  expect(values).not.toBeNull();
  expect(Number(values![1])).toBeCloseTo(x);
  expect(Number(values![2])).toBeCloseTo(y);
  expect(Number(values![3])).toBeCloseTo(zoom);
}

function pan(viewer: HTMLElement, x: number, y: number) {
  fireEvent(viewer, new MouseEvent("pointerdown", { bubbles: true, clientX: 500, clientY: 360 }));
  fireEvent(viewer, new MouseEvent("pointermove", { bubbles: true, clientX: 500 + x, clientY: 360 + y }));
  fireEvent(viewer, new MouseEvent("pointerup", { bubbles: true }));
}

describe("fullscreen zoom anchors", () => {
  it("keeps the point under an off-center cursor stationary when zooming", () => {
    const { image, viewer } = openViewer();
    fireEvent.wheel(viewer, { clientX: 700, clientY: 210, deltaY: -100 });
    expectTransform(image, -20, 15, 1.1);
  });

  it("keeps the cursor point stationary after panning and restores it on zoom out", () => {
    const { image, viewer } = openViewer();
    pan(viewer, 40, -30);
    fireEvent.wheel(viewer, { clientX: 700, clientY: 210, deltaY: -100 });
    expectTransform(image, 24, -18, 1.1);
    fireEvent.wheel(viewer, { clientX: 700, clientY: 210, deltaY: 100 });
    expectTransform(image, 40, -30, 1);
  });

  it("uses the visible viewport center for toolbar zoom after panning", async () => {
    const user = userEvent.setup();
    const { image, viewer } = openViewer();
    pan(viewer, 40, -30);
    await user.click(screen.getByLabelText("확대"));
    expectTransform(image, 50, -37.5, 1.25);
    await user.click(screen.getByLabelText("축소"));
    expectTransform(image, 40, -30, 1);
  });

  it("applies consecutive native wheel events to the latest zoom and position", () => {
    const { image, viewer } = openViewer();
    act(() => {
      viewer.dispatchEvent(new WheelEvent("wheel", { clientX: 700, clientY: 210, deltaY: -100 }));
      viewer.dispatchEvent(new WheelEvent("wheel", { clientX: 700, clientY: 210, deltaY: -100 }));
    });
    expectTransform(image, -42, 31.5, 1.21);
  });

  it("leaves the image position unchanged when zoom is already at a limit", async () => {
    const user = userEvent.setup();
    const { image, viewer } = openViewer();
    for (let index = 0; index < 12; index++) await user.click(screen.getByLabelText("확대"));
    expectTransform(image, 0, 0, 8);
    pan(viewer, 40, -30);
    fireEvent.wheel(viewer, { clientX: 700, clientY: 210, deltaY: -100 });
    expectTransform(image, 40, -30, 8);
    await user.click(screen.getByLabelText("화면 맞춤"));
    for (let index = 0; index < 10; index++) await user.click(screen.getByLabelText("축소"));
    pan(viewer, 40, -30);
    fireEvent.wheel(viewer, { clientX: 700, clientY: 210, deltaY: 100 });
    expectTransform(image, 40, -30, 0.25);
  });

  it("ignores wheel events without vertical movement", () => {
    const { image, viewer } = openViewer();
    fireEvent.wheel(viewer, { clientX: 700, clientY: 210, deltaX: 100, deltaY: 0 });
    expectTransform(image, 0, 0, 1);
  });

  it("preserves the cursor point when an event crosses either zoom limit", () => {
    const { image, viewer } = openViewer();
    act(() => {
      for (let index = 0; index < 25; index++) {
        viewer.dispatchEvent(new WheelEvent("wheel", { clientX: 700, clientY: 210, deltaY: -100 }));
      }
    });
    expectTransform(image, -1400, 1050, 8);
    act(() => {
      for (let index = 0; index < 40; index++) {
        viewer.dispatchEvent(new WheelEvent("wheel", { clientX: 700, clientY: 210, deltaY: 100 }));
      }
    });
    expectTransform(image, 150, -112.5, 0.25);
  });

  it("continues panning from the corrected position after zooming during a drag", () => {
    const { image, viewer } = openViewer();
    fireEvent(viewer, new MouseEvent("pointerdown", { bubbles: true, clientX: 500, clientY: 360 }));
    fireEvent(viewer, new MouseEvent("pointermove", { bubbles: true, clientX: 540, clientY: 330 }));
    fireEvent.wheel(viewer, { clientX: 700, clientY: 210, deltaY: -100 });
    fireEvent(viewer, new MouseEvent("pointermove", { bubbles: true, clientX: 550, clientY: 340 }));
    expectTransform(image, 34, -8, 1.1);
  });
});
