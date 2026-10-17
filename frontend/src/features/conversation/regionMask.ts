export type Stroke = { points: { x: number; y: number }[]; sizePx: number; erase: boolean };

export function drawSelection(canvas: HTMLCanvasElement, strokes: Stroke[]) {
  const context = canvas.getContext("2d");
  if (!context) return;
  const { width, height } = canvas;
  context.clearRect(0, 0, width, height);
  for (const stroke of strokes) {
    context.globalCompositeOperation = stroke.erase ? "destination-out" : "source-over";
    context.strokeStyle = "#83b4f2";
    context.lineCap = "round";
    context.lineJoin = "round";
    context.lineWidth = stroke.sizePx;
    context.beginPath();
    stroke.points.forEach((point, index) => {
      if (index) context.lineTo(point.x * width, point.y * height);
      else context.moveTo(point.x * width, point.y * height);
    });
    if (stroke.points.length === 1) {
      const point = stroke.points[0];
      context.lineTo(point.x * width + .01, point.y * height + .01);
    }
    context.stroke();
  }
  context.globalCompositeOperation = "source-over";
}

export function selectionPng(canvas: HTMLCanvasElement): string | null {
  const context = canvas.getContext("2d");
  if (!context) return null;
  const { width, height } = canvas;
  const mask = context.getImageData(0, 0, width, height);
  let selected = false;
  for (let index = 0; index < mask.data.length; index += 4) {
    const value = mask.data[index + 3] >= 128 ? 255 : 0;
    selected ||= value === 255;
    mask.data[index] = mask.data[index + 1] = mask.data[index + 2] = value;
    mask.data[index + 3] = 255;
  }
  if (!selected) return null;
  const output = document.createElement("canvas");
  output.width = width;
  output.height = height;
  const outputContext = output.getContext("2d");
  if (!outputContext) return null;
  outputContext.putImageData(mask, 0, 0);
  return output.toDataURL("image/png");
}
