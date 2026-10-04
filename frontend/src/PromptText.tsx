import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import { WandSparkles } from "lucide-react";

export default function PromptText({
  children,
  follow = false,
}: {
  children: ReactNode;
  follow?: boolean;
}) {
  const panel = useRef<HTMLSpanElement>(null);
  const following = useRef(true);
  useEffect(() => {
    if (follow && panel.current && following.current)
      panel.current.scrollTop = panel.current.scrollHeight;
  }, [children, follow]);
  return (
    <span className="prompt-text">
      <span className="stream-label">
        <WandSparkles size={14} aria-hidden="true" /> 생성 프롬프트
      </span>
      <span
        className="prompt-content"
        ref={panel}
        onScroll={(event) => {
          const element = event.currentTarget;
          following.current =
            element.scrollHeight - element.scrollTop - element.clientHeight < 24;
        }}
      >
        {children}
      </span>
    </span>
  );
}
