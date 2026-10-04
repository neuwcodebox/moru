import { useEffect, useState } from "react";
import { LoaderCircle, WandSparkles } from "lucide-react";
import { call } from "./api";
import type { ImageDetails } from "./api";

export default function ImagePreview({
  id,
  source,
  onOpen,
  onFocus,
  onLoad,
}: {
  id: string;
  source: string;
  onOpen: () => void;
  onFocus: () => void;
  onLoad: () => void;
}) {
  const [revealed, setRevealed] = useState(false);
  const [prompt, setPrompt] = useState<string | null>(null);
  const [error, setError] = useState("");
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
      aria-label="이미지 전체 화면 보기"
      onClick={onOpen}
      onMouseEnter={() => setRevealed(true)}
      onMouseLeave={() => setRevealed(false)}
      onFocus={() => {
        onFocus();
        setRevealed(true);
      }}
      onBlur={() => setRevealed(false)}
    >
      <img src={source} alt="생성 이미지" onLoad={onLoad} />
      <span className={`image-prompt-overlay ${revealed ? "revealed" : ""}`} aria-hidden={!revealed}>
        <span className="stream-label"><WandSparkles size={14} /> 생성 프롬프트</span>
        <span className="prompt-content">
          {error || prompt || <LoaderCircle className="spinner" size={18} />}
        </span>
      </span>
    </button>
  );
}
