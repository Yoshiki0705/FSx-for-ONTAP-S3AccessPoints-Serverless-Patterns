/**
 * H-2: Exponential backoff retry utility for S3 AP throttling (429 SlowDown).
 *
 * When the portal hits S3 AP rate limits, this utility automatically retries
 * with exponential backoff and provides a callback for UI status updates
 * (e.g., showing "Retrying..." banner).
 */

export interface RetryOptions {
  /** Maximum number of retry attempts (default: 3) */
  maxRetries?: number;
  /** Initial delay in ms (default: 1000) */
  baseDelay?: number;
  /** Maximum delay in ms (default: 10000) */
  maxDelay?: number;
  /** Callback when a retry occurs — use for UI feedback */
  onRetry?: (attempt: number, delay: number, error: unknown) => void;
  /** Callback when all retries are exhausted */
  onExhausted?: (error: unknown) => void;
}

/**
 * Execute an async function with exponential backoff retry.
 *
 * Retries on:
 * - Network errors (fetch failures)
 * - 429 Too Many Requests (S3 AP SlowDown)
 * - 5xx Server errors
 *
 * Does NOT retry on:
 * - 4xx Client errors (except 429)
 * - Validation errors
 */
export async function retryWithBackoff<T>(
  fn: () => Promise<T>,
  options: RetryOptions = {}
): Promise<T> {
  const {
    maxRetries = 3,
    baseDelay = 1000,
    maxDelay = 10000,
    onRetry,
    onExhausted,
  } = options;

  let lastError: unknown;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;

      // Don't retry on non-retriable errors
      if (!isRetriable(error)) {
        throw error;
      }

      if (attempt === maxRetries) {
        onExhausted?.(error);
        throw error;
      }

      // Exponential backoff with jitter
      const delay = Math.min(
        baseDelay * Math.pow(2, attempt) + Math.random() * 500,
        maxDelay
      );

      onRetry?.(attempt + 1, delay, error);

      await new Promise((resolve) => setTimeout(resolve, delay));
    }
  }

  throw lastError;
}

function isRetriable(error: unknown): boolean {
  if (error instanceof Error) {
    const message = error.message.toLowerCase();
    // S3 AP SlowDown / throttling
    if (message.includes("slowdown") || message.includes("429") || message.includes("throttl")) {
      return true;
    }
    // Network errors
    if (message.includes("network") || message.includes("timeout") || message.includes("econnreset")) {
      return true;
    }
    // Server errors (5xx)
    if (message.includes("500") || message.includes("502") || message.includes("503")) {
      return true;
    }
  }
  return false;
}

/**
 * React hook-friendly wrapper that tracks retry state.
 *
 * Usage in component:
 *   const [retryState, setRetryState] = useState<RetryState>({ retrying: false });
 *   const result = await retryWithBackoff(fetchFn, {
 *     onRetry: (attempt, delay) => setRetryState({ retrying: true, attempt, nextRetryMs: delay }),
 *     onExhausted: () => setRetryState({ retrying: false, exhausted: true }),
 *   });
 */
export interface RetryState {
  retrying: boolean;
  attempt?: number;
  nextRetryMs?: number;
  exhausted?: boolean;
}
