import type { CSSProperties } from "react";

export function imageFrameStyle(width: number, height: number): CSSProperties {
  return {
    width: `min(100%, ${Math.min(width, 550, (520 * width) / height)}px)`,
    aspectRatio: `${width} / ${height}`,
  };
}
