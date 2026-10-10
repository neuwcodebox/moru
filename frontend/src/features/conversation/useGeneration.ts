import { useEffect, useState } from "react";
import { call } from "../../api";
import type { Job, Project } from "../../api";

type GenerationMethod = "submit_request" | "regenerate" | "retry_request" | "generate_from_prompt";

export function useGeneration({ onProject, onError, onComplete }: {
  onProject: (project: Project) => void;
  onError: (error: unknown) => void;
  onComplete: () => void;
}) {
  const [job, setJob] = useState<Job | null>(null);
  const [stopping, setStopping] = useState(false);

  useEffect(() => {
    if (!job) return;
    const jobId = job.id;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const result = await call<Job>("get_job", jobId);
        if (disposed) return;
        if (["completed", "failed", "cancelled"].includes(result.state)) {
          const refreshed = await call<Project>("get_project", result.project_id);
          if (disposed) return;
          onProject(refreshed);
          setJob(null);
          setStopping(false);
          onComplete();
          return;
        }
        setJob(result);
      } catch (error) {
        if (!disposed) onError(error ?? { code: "PROGRESS_FAILED" });
      }
      if (!disposed) timer = setTimeout(poll, 300);
    }
    void poll();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [job?.id, onProject, onError, onComplete]);

  async function startGeneration(method: GenerationMethod, ...args: unknown[]) {
    const next = await call<Job>(method, ...args);
    setJob(next);
    try {
      onProject(await call<Project>("get_project", next.project_id));
    } catch (error) {
      // Admission succeeded: keep observing the job even if its conversation cannot refresh.
      onError(error ?? { code: "CONVERSATION_LOAD_FAILED" });
    }
  }

  function cancelGeneration() {
    if (!job || stopping) return;
    setStopping(true);
    void call("cancel_job", job.id).catch((error) => {
      setStopping(false);
      onError(error ?? { code: "CANCEL_FAILED" });
    });
  }

  return { job, stopping, startGeneration, cancelGeneration };
}
