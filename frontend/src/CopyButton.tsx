import { useEffect, useState } from "react";
import { Check, Copy, LoaderCircle } from "lucide-react";

export default function CopyButton({
  onCopy,
  onError,
  disabled = false,
}: {
  onCopy: () => Promise<void>;
  onError: (message: string) => void;
  disabled?: boolean;
}) {
  const [state, setState] = useState<"idle" | "pending" | "copied">("idle");
  useEffect(() => {
    if (state !== "copied") return;
    const timer = setTimeout(() => setState("idle"), 1600);
    return () => clearTimeout(timer);
  }, [state]);
  return (
    <button
      type="button"
      className={`copy-button ${state}`}
      aria-label={state === "copied" ? "복사 완료" : "복사"}
      title={state === "copied" ? "복사했습니다." : "복사"}
      disabled={disabled || state === "pending"}
      onClick={async () => {
        setState("pending");
        try {
          await onCopy();
          setState("copied");
        } catch (error) {
          setState("idle");
          onError(error instanceof Error ? error.message : "복사할 수 없습니다.");
        }
      }}
    >
      <span className="copy-symbol" key={state} aria-hidden="true">
        {state === "copied" ? <Check size={15} /> : state === "pending"
          ? <LoaderCircle size={15} className="spinner" /> : <Copy size={15} />}
      </span>
      복사
      <span className="sr-only" role="status">
        {state === "copied" ? "복사했습니다." : ""}
      </span>
    </button>
  );
}
