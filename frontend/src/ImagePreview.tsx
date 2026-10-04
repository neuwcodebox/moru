import { useEffect, useRef, useState } from "react";
import { LoaderCircle } from "lucide-react";
import { call } from "./api";
import type { ImageDetails } from "./api";
import PromptText from "./PromptText";
import { imageFrameStyle } from "./imageFrame";

export default function ImagePreview({
  id,
  source,
  width,
  height,
  inactive,
  onOpen,
  onFocus,
  onLoad,
}: {
  id: string;
  source: string;
  width: number;
  height: number;
  inactive: boolean;
  onOpen: () => void;
  onFocus: () => void;
  onLoad: () => void;
}) {
  const [revealed, setRevealed] = useState(false);
  const [prompt, setPrompt] = useState<string | null>(null);
  const [error, setError] = useState("");
  const suppressReveal = useRef(false);
  useEffect(() => {
    if (inactive) {
      suppressReveal.current = true;
      setRevealed(false);
    }
    function keyboardFocus(event: KeyboardEvent) {
      if (!inactive && event.key === "Tab") suppressReveal.current = false;
    }
    // Tab may start outside this image; restored modal focus must stay suppressed.
    document.addEventListener("keydown", keyboardFocus, true);
    return () => document.removeEventListener("keydown", keyboardFocus, true);
  }, [inactive]);
  useEffect(() => {
    if (!revealed || prompt !== null) return;
    let current = true;
    setError("");
    call<ImageDetails>("get_image_details", id)
      .then((details) => {
        if (current) setPrompt(details.prompt);
      })
      .catch((error) => {
        if (current) setError(error instanceof Error ? error.message : "프롬프트를 불러올 수 없습니다.");
      });
    return () => { current = false; };
  }, [id, revealed, prompt]);
  return (
    <button
      className="image-button"
      style={imageFrameStyle(width, height)}
      aria-label="이미지 전체 화면 보기"
      onClick={() => {
        suppressReveal.current = true;
        setRevealed(false);
        onOpen();
      }}
      onMouseEnter={() => {
        if (!inactive && !suppressReveal.current) setRevealed(true);
      }}
      onMouseMove={() => {
        if (inactive) return;
        suppressReveal.current = false;
        setRevealed(true);
      }}
      onMouseLeave={() => setRevealed(false)}
      onFocus={() => {
        onFocus();
        if (!inactive && !suppressReveal.current) setRevealed(true);
      }}
      onBlur={() => setRevealed(false)}
    >
      <img src={source} alt="생성 이미지" onLoad={onLoad} />
      <span className={`image-prompt-overlay ${revealed ? "revealed" : ""}`} aria-hidden={!revealed}>
        <PromptText>
          {error || prompt || <LoaderCircle className="spinner" size={18} />}
        </PromptText>
      </span>
    </button>
  );
}
