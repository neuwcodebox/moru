import { expect, it, vi } from "vitest";
import { selectionPng } from "./regionMask";

function selection(pixels: number[]) {
  const canvas = document.createElement("canvas");
  canvas.width = 2;
  canvas.height = 2;
  const context = {
    getImageData: vi.fn(() => ({ data: new Uint8ClampedArray(pixels) })),
    putImageData: vi.fn(),
  };
  const getContext = vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(context as never);
  const encode = vi.spyOn(HTMLCanvasElement.prototype, "toDataURL").mockReturnValue("data:image/png;base64,MASK");
  return { canvas, context, getContext, encode };
}

it("exports an opaque binary mask from selection alpha at the original canvas size", () => {
  const { canvas, context, encode } = selection([
    131, 180, 242, 255, 255, 255, 255, 0,
    131, 180, 242, 127, 0, 0, 0, 128,
  ]);
  expect(selectionPng(canvas)).toBe("data:image/png;base64,MASK");
  expect(context.getImageData).toHaveBeenCalledWith(0, 0, 2, 2);
  const [mask, x, y] = context.putImageData.mock.calls[0];
  expect([x, y]).toEqual([0, 0]);
  expect(Array.from(mask.data)).toEqual([
    255, 255, 255, 255, 0, 0, 0, 255,
    0, 0, 0, 255, 255, 255, 255, 255,
  ]);
  const output = encode.mock.contexts[0] as HTMLCanvasElement;
  expect([output.width, output.height]).toEqual([2, 2]);
  expect(encode).toHaveBeenCalledWith("image/png");
});

it("returns no mask when all pixels are transparent or below the selection threshold", () => {
  const { canvas, encode } = selection([
    255, 255, 255, 0, 131, 180, 242, 127,
    131, 180, 242, 0, 255, 255, 255, 1,
  ]);
  expect(selectionPng(canvas)).toBeNull();
  expect(encode).not.toHaveBeenCalled();
});

it.each(["source", "output"])("returns no mask when the %s canvas context is unavailable", (missing) => {
  const { canvas, context, getContext, encode } = selection([0, 0, 0, 255]);
  getContext.mockReturnValueOnce(missing === "source" ? null : context as never)
    .mockReturnValueOnce(null);
  expect(selectionPng(canvas)).toBeNull();
  expect(encode).not.toHaveBeenCalled();
});
