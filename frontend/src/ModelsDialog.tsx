import { useEffect, useState } from "react";
import { call } from "./api";
import type { ModelStatus } from "./api";
import Modal from "./Modal";

const names: Record<string, string> = {
  prompt: "프롬프트 작성 모델",
  "anima-turbo-v1.1": "Anima Turbo",
  "anima-aesthetic-v1.1": "Anima Aesthetic",
  text_encoder: "문장 이해 모델",
  vae: "이미지 복원 모델",
};
export default function ModelsDialog({
  initial,
  onUpdate,
  onClose,
}: {
  initial: ModelStatus[];
  onUpdate: (models: ModelStatus[]) => void;
  onClose: () => void;
}) {
  const [models, setModels] = useState(initial);
  const [error, setError] = useState("");
  const [acting, setActing] = useState(false);
  const downloading = models.some((model) =>
    ["queued", "downloading"].includes(model.download?.state ?? ""),
  );
  useEffect(() => {
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const fresh = await call<ModelStatus[]>("get_model_status");
        if (disposed) return;
        setModels(fresh);
        onUpdate(fresh);
      } catch (error) {
        if (!disposed)
          setError(
            error instanceof Error
              ? error.message
              : "모델 상태를 확인할 수 없습니다.",
          );
      }
      if (!disposed) timer = setTimeout(poll, 500);
    }
    void poll();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, []);
  async function action(method: string, id: string) {
    setActing(true);
    setError("");
    try {
      const fresh = await call<ModelStatus[]>(method, id);
      setModels(fresh);
      onUpdate(fresh);
    } catch (error) {
      setError(
        error instanceof Error ? error.message : "모델을 준비할 수 없습니다.",
      );
    } finally {
      setActing(false);
    }
  }
  return (
    <Modal title="모델 준비" onClose={onClose}>
      <p className="hint">
        필요한 모델을 다운로드하거나 이미 가지고 있는 파일을 선택하세요.
      </p>
      <div className="model-list">
        {models.map((model) => {
          const d = model.download;
          const active = d && ["queued", "downloading"].includes(d.state);
          return (
            <div className="model-row" key={model.id}>
              <div className="model-label">
                <strong>{names[model.id]}</strong>
                <span className="hint">
                  {model.available ? "준비됨" : "준비 필요"}
                </span>
              </div>
              {active ? (
                <div className="download-progress">
                  <progress
                    value={d.received}
                    max={d.total}
                    aria-label={`${names[model.id]} 다운로드 진행률`}
                  />
                  <span>{Math.floor((d.received * 100) / d.total)}%</span>
                  <button
                    disabled={acting}
                    onClick={() =>
                      void action("cancel_model_download", model.id)
                    }
                  >
                    취소
                  </button>
                </div>
              ) : (
                <div className="model-actions">
                  <button
                    disabled={acting || downloading}
                    onClick={() => void action("select_local_model", model.id)}
                  >
                    파일 선택
                  </button>
                  {!model.available && (
                    <button
                      disabled={acting || downloading}
                      onClick={() => void action("download_model", model.id)}
                    >
                      다운로드
                    </button>
                  )}
                </div>
              )}
              {d?.message && <p role="alert">{d.message}</p>}
            </div>
          );
        })}
      </div>
      {error && <p role="alert">{error}</p>}
      <div className="modal-actions">
        <button onClick={onClose}>닫기</button>
      </div>
    </Modal>
  );
}
