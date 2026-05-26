import { FormEvent, useCallback, useState } from "react";
import { createProject } from "../api/projects";
import { createThreadMessage } from "../api/thread";
import type { DesignBriefReadyEvent } from "../api/types";
import { PIPELINE_PROGRESS } from "../api/types";
import { DesignBrief } from "../features/pipeline/DesignBrief";
import { useProjectStream } from "../hooks/useProjectStream";
import "./ProjectsPage.css";

type PipelinePhase = "form" | "exiting" | "analysing" | "brief";

const EXIT_MS = 300;

export function ProjectsPage() {
  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [phase, setPhase] = useState<PipelinePhase>("form");
  const [locked, setLocked] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [streamProjectId, setStreamProjectId] = useState<number | null>(null);
  const [progress, setProgress] = useState(0);
  const [progressPulse, setProgressPulse] = useState(false);
  const [brief, setBrief] = useState<DesignBriefReadyEvent | null>(null);

  const handleSse = useCallback((event: Record<string, unknown>) => {
    if (event.type !== "design_brief_ready") return;
    const payload = event as DesignBriefReadyEvent;
    setBrief(payload);
    setProgress(PIPELINE_PROGRESS.briefReady);
    setProgressPulse(false);
    setPhase("brief");
  }, []);

  useProjectStream(streamProjectId, handleSse);

  const createAndRun = async (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !prompt.trim() || locked) return;

    setLocked(true);
    setError(null);
    setBrief(null);
    setProgress(0);
    setProgressPulse(true);
    setPhase("exiting");

    const showAnalysing = window.setTimeout(() => {
      setPhase("analysing");
    }, EXIT_MS);

    try {
      const project = await createProject(name.trim());
      setStreamProjectId(project.id);
      await createThreadMessage(project.id, prompt.trim());
    } catch (err) {
      window.clearTimeout(showAnalysing);
      setPhase("form");
      setLocked(false);
      setProgressPulse(false);
      setProgress(0);
      setStreamProjectId(null);
      setError(err instanceof Error ? err.message : "Failed to start pipeline");
    }
  };

  const inPipeline = phase !== "form";
  const showForm = phase === "form" || phase === "exiting";
  const showAnalysing = phase === "analysing";
  const showBrief = phase === "brief" && brief != null;

  return (
    <div
      className={`projects-page${inPipeline ? " projects-page--pipeline" : ""}`}
    >
      <section className="pipeline-stage" aria-live="polite">
        {inPipeline ? (
          <div className="pipeline-stage__track" aria-hidden>
            <div
              className={`pipeline-stage__fill${progressPulse ? " pipeline-stage__fill--pulse" : ""}`}
              style={{ width: `${progress}%` }}
            />
          </div>
        ) : null}

        <div className="pipeline-stage__body">
          {showForm ? (
            <div
              className={`pipeline-form panel${phase === "exiting" ? " pipeline-form--exit" : ""}`}
            >
              <h1 className="pipeline-form__title">New project</h1>
              <p className="pipeline-form__desc">
                Name your project and describe what you want to build.
              </p>

              <form
                className="pipeline-form__fields"
                onSubmit={(e) => void createAndRun(e)}
                noValidate
              >
                <div className="field">
                  <label className="field-label" htmlFor="project-name">
                    Project name
                  </label>
                  <input
                    id="project-name"
                    className="field-input"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="e.g. Marketing site"
                    required
                    disabled={locked}
                  />
                </div>

                <div className="field">
                  <label className="field-label" htmlFor="design-prompt">
                    Design prompt
                  </label>
                  <textarea
                    id="design-prompt"
                    className="field-input field-textarea pipeline-form__prompt"
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    placeholder="Describe the UI, brand feel, and components you need…"
                    required
                    disabled={locked}
                  />
                </div>

                {error ? (
                  <div className="form-alert" role="alert">
                    <span className="form-alert__icon" aria-hidden>
                      ⚠
                    </span>
                    <p className="form-alert__text">{error}</p>
                  </div>
                ) : null}

                <button
                  type="submit"
                  className="btn btn-cta"
                  disabled={locked}
                >
                  Create &amp; run pipeline
                </button>
              </form>
            </div>
          ) : null}

          {showAnalysing ? (
            <p className="pipeline-status">
              <span className="pipeline-status__text">
                Analysing your inputs…
              </span>
            </p>
          ) : null}

          {showBrief ? <DesignBrief data={brief} /> : null}
        </div>
      </section>
    </div>
  );
}
