import { useQuery } from "@tanstack/react-query";
import { thumbnailQuery } from "../lib/dispatch";

/**
 * Extensions the thumbnail function can actually render.
 *
 * Deliberately not the list `FilePreview` uses to decide what it can *open*. That one
 * includes `.svg`, which Pillow cannot rasterise, and omits `.tif`, which it can read
 * -- so reusing it would ask the backend for thumbnails it always skips and never ask
 * for ones it could produce. Both mistakes are invisible: the first wastes an
 * invocation per SVG, the second just leaves an icon where a picture belonged.
 *
 * `tests/lib/thumbnails.test.ts` reads the tuple out of the handler and asserts this
 * list matches it, so the two cannot drift apart quietly.
 */
export const THUMBNAIL_EXTENSIONS = [
  ".jpg",
  ".jpeg",
  ".png",
  ".gif",
  ".bmp",
  ".webp",
  ".tif",
  ".tiff",
] as const;

/** Whether a thumbnail is worth asking for. */
export function isThumbnailable(name: string): boolean {
  const lowered = name.toLowerCase();
  return THUMBNAIL_EXTENSIONS.some((extension) => lowered.endsWith(extension));
}

interface ThumbnailResponse {
  thumbnails?: Record<string, string>;
  /** Keys whose thumbnail was not built this time, because the budget was spent. */
  pending?: string[];
  /** Keys that will never have one, mapped to why. */
  skipped?: Record<string, string>;
  expiresIn?: number;
}

/** How long to wait before asking again for the keys that came back pending. */
const PENDING_RETRY_MS = 4000;

/**
 * Thumbnail URLs for the image files on the current page.
 *
 * One request for the page, not one per row. A URL per file would cost an invocation
 * per row and then make the browser download each full-size original to draw
 * something the width of a fingertip.
 *
 * The query key is the sorted list of image keys, so navigating to a folder with the
 * same pictures reuses the answer, and navigating to a different one asks again.
 *
 * `pending` is polled rather than ignored. The backend caps how many images it
 * generates per invocation so a cold folder cannot time out, which means the first
 * response for a folder nobody has opened is mostly pending -- and without a second
 * ask the icons would simply stay.
 */
export function useThumbnails(fileKeys: string[]): {
  urlFor: (key: string) => string | undefined;
  loading: boolean;
} {
  // Sorted so two renders of the same page produce one cache entry rather than two.
  const wanted = fileKeys.filter(isThumbnailable).sort();

  const { data, isFetching } = useQuery({
    queryKey: ["thumbnails", wanted],
    enabled: wanted.length > 0,
    // A URL is signed for a limited time, so holding it past that serves broken
    // images. Refetching a little before expiry is cheaper than checking each one.
    staleTime: 10 * 60 * 1000,
    // `isFetching` below, never `isPending`: a disabled query stays pending forever
    // because it has no data. Nothing here renders a spinner on it, but the value is
    // returned to callers and a caller could.
    // query-gate-checked: isFetching is what the caller receives as `loading`
    refetchInterval: (query) => {
      const pending = query.state.data?.pending ?? [];
      return pending.length > 0 ? PENDING_RETRY_MS : false;
    },
    // The endpoint helper rather than `unwrap(dispatch(...))`: it returns the parsed
    // payload with `error` left in place, which is the behaviour wanted here.
    // `unwrap` throws on a failure payload, and a thumbnail that could not be built
    // is not an error worth propagating -- the row keeps its icon and the page is
    // unaffected.
    queryFn: () =>
      thumbnailQuery<ThumbnailResponse>({
        action: "getThumbnails",
        params: { keys: wanted },
      }).then((payload) => payload ?? {}),
  });

  const urls = data?.thumbnails ?? {};
  return {
    urlFor: (key: string) => urls[key],
    loading: isFetching,
  };
}
