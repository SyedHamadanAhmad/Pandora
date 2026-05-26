import {
  type ChangeEvent,
  FormEvent,
  useCallback,
  useId,
  useRef,
  useState,
} from "react";
import { createProject } from "../api/projects";
import {
  createThreadMessage,
  MAX_THREAD_IMAGES,
  MAX_THREAD_REF_URLS,
} from "../api/thread";
import { useToast } from "../components/Toast/ToastContext";
import {
  initialPipelineRunState,
  reducePipelineSse,
} from "../features/pipeline/pipelineRunState";
import { PipelineResultsCarousel } from "../features/pipeline/PipelineResultsCarousel";
import { useProjectStream } from "../hooks/useProjectStream";
import { extractRefUrlsFromText } from "../utils/extractRefUrls";
import "./ProjectsPage.css";

type PipelinePhase = "form" | "exiting" | "analysing";

const EXIT_MS = 300;

function truncateUrlDisplay(url: string, maxLen = 40): string {
  if (url.length <= maxLen) return url;
  const keep = Math.floor((maxLen - 1) / 2);
  return `${url.slice(0, keep)}…${url.slice(-keep)}`;
}

export function ProjectsPage() {
  const [name, setName] = useState("");
  const [prompt, setPrompt] = useState("");
  const [refUrls, setRefUrls] = useState<string[]>([]);
  const [imageFiles, setImageFiles] = useState<File[]>([]);
  const [phase, setPhase] = useState<PipelinePhase>("form");
  const [locked, setLocked] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [streamProjectId, setStreamProjectId] = useState<number | null>(null);
  const [run, setRun] = useState(initialPipelineRunState);

  const imageInputRef = useRef<HTMLInputElement>(null);
  const imageInputId = useId();
  const toast = useToast();

  const handleSse = useCallback((event: Record<string, unknown>) => {
    setRun((prev) => reducePipelineSse(prev, event));
  }, []);

  useProjectStream(streamProjectId, handleSse);

  const onPromptChange = (value: string) => {
    const { nextText, added, rejected } = extractRefUrlsFromText(
      value,
      refUrls,
      MAX_THREAD_REF_URLS,
    );
    if (added.length > 0) {
      setRefUrls((prev) => [...prev, ...added]);
    }
    if (rejected.length > 0) {
      toast.warning(
        `Only ${MAX_THREAD_REF_URLS} reference links can be attached. Remove one to add another.`,
      );
    }
    setPrompt(nextText);
  };

  const removeRefUrl = (url: string) => {
    setRefUrls((prev) => prev.filter((u) => u !== url));
  };

  const onImagePick = (e: ChangeEvent<HTMLInputElement>) => {
    const picked = [...(e.target.files ?? [])];
    e.target.value = "";
    if (picked.length === 0) return;

    setImageFiles((prev) => {
      const slots = MAX_THREAD_IMAGES - prev.length;
      if (slots <= 0) {
        toast.warning(
          `Only ${MAX_THREAD_IMAGES} images can be attached. Remove one to add another.`,
        );
        return prev;
      }
      const accepted = picked.slice(0, slots);
      const rejectedCount = picked.length - accepted.length;
      if (rejectedCount > 0) {
        toast.warning(
          rejectedCount === 1
            ? `Only ${MAX_THREAD_IMAGES} images allowed — 1 file was not added.`
            : `Only ${MAX_THREAD_IMAGES} images allowed — ${rejectedCount} files were not added.`,
        );
      }
      return [...prev, ...accepted];
    });
  };

  const removeImageAt = (index: number) => {
    setImageFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const canSubmit =
    Boolean(name.trim()) && Boolean(prompt.trim()) && !locked;

  const createAndRun = async (e: FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;

    setLocked(true);
    setError(null);
    setRun({ ...initialPipelineRunState(), progressPulse: true });
    setPhase("exiting");

    const showAnalysing = window.setTimeout(() => {
      setPhase("analysing");
    }, EXIT_MS);

    try {
      const project = await createProject(name.trim());
      setStreamProjectId(project.id);
      await createThreadMessage(project.id, {
        content: prompt.trim(),
        urls: refUrls.length > 0 ? refUrls : undefined,
        images: imageFiles.length > 0 ? imageFiles : undefined,
      });
    } catch (err) {
      window.clearTimeout(showAnalysing);
      setPhase("form");
      setLocked(false);
      setRun(initialPipelineRunState());
      setStreamProjectId(null);
      setError(err instanceof Error ? err.message : "Failed to start pipeline");
    }
  };

  const inPipeline = phase !== "form";
  const showForm = phase === "form" || phase === "exiting";
  const showAnalysing = phase === "analysing" && run.brief == null;
  const showResultsCarousel = run.brief != null;

  return (
    <div
      className={`projects-page${inPipeline ? " projects-page--pipeline" : ""}`}
    >
      <section className="pipeline-stage" aria-live="polite">
        {inPipeline ? (
          <div className="pipeline-stage__track" aria-hidden>
            <div
              className={`pipeline-stage__fill${run.progressPulse ? " pipeline-stage__fill--pulse" : ""}`}
              style={{ width: `${run.progress}%` }}
            />
          </div>
        ) : null}

        <div className="pipeline-stage__body pipeline-stage__body--stack">
          {showForm ? (
            <div
              className={`pipeline-form panel${phase === "exiting" ? " pipeline-form--exit" : ""}`}
            >
              <h1 className="pipeline-form__title">New project</h1>
              <p className="pipeline-form__desc">
                Name your project and describe what you want to build. Paste
                reference URLs or add images (optional).
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
                    Design prompt <span className="field-required">(required)</span>
                  </label>
                  <div className="pipeline-prompt-shell">
                    <textarea
                      id="design-prompt"
                      className="field-input field-textarea pipeline-form__prompt"
                      value={prompt}
                      onChange={(e) => onPromptChange(e.target.value)}
                      placeholder="Describe the UI, brand feel, and components you need. You can paste https://… links here."
                      required
                      disabled={locked}
                    />
                    <div className="pipeline-prompt-shell__footer">
                      {refUrls.length > 0 ? (
                        <ul
                          className="ref-url-badges"
                          aria-label="Attached reference URLs"
                        >
                          {refUrls.map((url) => (
                            <li key={url} className="ref-url-badges__item">
                              <span className="ref-url-badge" title={url}>
                                <span className="ref-url-badge__text">
                                  {truncateUrlDisplay(url)}
                                </span>
                                <button
                                  type="button"
                                  className="ref-url-badge__remove"
                                  aria-label={`Remove ${url}`}
                                  disabled={locked}
                                  onClick={() => removeRefUrl(url)}
                                >
                                  ×
                                </button>
                              </span>
                            </li>
                          ))}
                        </ul>
                      ) : null}
                      <div className="pipeline-prompt-shell__row">
                        <input
                          ref={imageInputRef}
                          id={imageInputId}
                          type="file"
                          className="visually-hidden"
                          accept="image/jpeg,image/png,image/webp,image/gif"
                          multiple
                          disabled={locked}
                          onChange={onImagePick}
                        />
                        <button
                          type="button"
                          className="ref-images-cta"
                          disabled={locked}
                          onClick={() => {
                            if (imageFiles.length >= MAX_THREAD_IMAGES) {
                              toast.warning(
                                `Only ${MAX_THREAD_IMAGES} images can be attached. Remove one to add another.`,
                              );
                              return;
                            }
                            imageInputRef.current?.click();
                          }}
                        >
                          Add images
                        </button>
                        <span className="ref-attachments-meta">
                          {refUrls.length}/{MAX_THREAD_REF_URLS} links
                          {" · "}
                          {imageFiles.length}/{MAX_THREAD_IMAGES} images
                        </span>
                      </div>
                      {imageFiles.length > 0 ? (
                        <ul
                          className="ref-image-chips"
                          aria-label="Attached images"
                        >
                          {imageFiles.map((file, i) => (
                            <li key={`${file.name}-${i}`} className="ref-image-chip">
                              <span className="ref-image-chip__name">
                                {file.name}
                              </span>
                              <button
                                type="button"
                                className="ref-image-chip__remove"
                                aria-label={`Remove ${file.name}`}
                                disabled={locked}
                                onClick={() => removeImageAt(i)}
                              >
                                ×
                              </button>
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  </div>
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
                  disabled={!canSubmit}
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

          {showResultsCarousel && run.brief ? (
            <PipelineResultsCarousel
              brief={run.brief}
              schema={run.schema}
              components={run.components}
            />
          ) : null}
        </div>
      </section>
    </div>
  );
}
