/** Must match `MAX_REFERENCE_URLS` in `backend/app/routers/thread.py`. */
export const MAX_THREAD_REF_URLS = 3;

/** Must match `MAX_IMAGES_PER_REQUEST` in `backend/app/services/storage_service.py`. */
export const MAX_THREAD_IMAGES = 5;

export interface CreateThreadMessageOptions {
  /** Plain-text design prompt (optional if urls or images provided). */
  content?: string;
  /** Reference URLs (max {@link MAX_THREAD_REF_URLS}). */
  urls?: string[];
  /** Image files (max {@link MAX_THREAD_IMAGES} per request). */
  images?: File[];
}
