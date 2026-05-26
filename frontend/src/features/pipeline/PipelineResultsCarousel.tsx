import { useCallback, useEffect, useRef, useState } from "react";
import type { DesignBriefReadyEvent, SchemaReadyEvent } from "../../api/types";
import { ComponentBuildList } from "./ComponentBuildList";
import { DesignBrief } from "./DesignBrief";
import type { ComponentRow } from "./pipelineRunState";
import "./PipelineResultsCarousel.css";

/** Must match `pipeline-slide-out` duration in PipelineResultsCarousel.css */
const SLIDE_TRANSITION_MS = 280;

interface PipelineResultsCarouselProps {
  brief: DesignBriefReadyEvent;
  schema: SchemaReadyEvent | null;
  components: ComponentRow[];
}

export function PipelineResultsCarousel({
  brief,
  schema,
  components,
}: PipelineResultsCarouselProps) {
  const [slide, setSlide] = useState<0 | 1>(0);
  const [isExiting, setIsExiting] = useState(false);
  const transitioningRef = useRef(false);
  const autoAdvancedRef = useRef(false);
  const schemaReady = schema != null && components.length > 0;

  const goToSlide = useCallback((next: 0 | 1) => {
    if (transitioningRef.current) return;

    setSlide((current) => {
      if (next === current) return current;

      transitioningRef.current = true;
      setIsExiting(true);
      window.setTimeout(() => {
        setSlide(next);
        setIsExiting(false);
        transitioningRef.current = false;
      }, SLIDE_TRANSITION_MS);

      return current;
    });
  }, []);

  useEffect(() => {
    if (schemaReady && !autoAdvancedRef.current) {
      autoAdvancedRef.current = true;
      goToSlide(1);
    }
  }, [schemaReady, schema?.pipelineId, goToSlide]);

  const showPrev = slide === 1 && !isExiting;
  const showNext = slide === 0 && schemaReady && !isExiting;
  const navDisabled = isExiting;

  const panelClass = (exiting: boolean) =>
    `pipeline-carousel__panel${exiting ? " pipeline-carousel__panel--exit" : ""}`;

  return (
    <div className="pipeline-carousel" aria-label="Pipeline results">
      <button
        type="button"
        className={`pipeline-carousel__nav pipeline-carousel__nav--prev${showPrev ? "" : " pipeline-carousel__nav--hidden"}`}
        aria-label="Previous slide: design brief"
        disabled={!showPrev || navDisabled}
        onClick={() => goToSlide(0)}
      >
        ‹
      </button>

      <div className="pipeline-carousel__viewport">
        {slide === 0 ? (
          <div
            key="brief"
            className={panelClass(isExiting)}
            id="pipeline-slide-brief"
          >
            <DesignBrief data={brief} />
          </div>
        ) : schemaReady && schema ? (
          <div
            key="components"
            className={panelClass(isExiting)}
            id="pipeline-slide-schema"
          >
            <ComponentBuildList
              rows={components}
              componentCount={schema.componentCount}
            />
          </div>
        ) : null}
      </div>

      <button
        type="button"
        className={`pipeline-carousel__nav pipeline-carousel__nav--next${showNext ? "" : " pipeline-carousel__nav--hidden"}`}
        aria-label="Next slide: components"
        disabled={!showNext || navDisabled}
        onClick={() => goToSlide(1)}
      >
        ›
      </button>
    </div>
  );
}
