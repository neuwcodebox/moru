import { useEffect, useState } from "react";
import { Check, Copy, LoaderCircle } from "lucide-react";

export default function CopyButton({
  label = "복사",
  onCopy,
  onError,
  disabled = false,
}: {
  label?: string;
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
      aria-label={state === "copied" ? `${label} 완료` : label}
      title={state === "copied" ? "복사했습니다." : label}
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
      {label}
      <span className="sr-only" role="status">
        {state === "copied" ? "복사했습니다." : ""}
      </span>
    </button>
  );
}
