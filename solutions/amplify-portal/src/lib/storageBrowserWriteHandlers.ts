/**
 * Write handlers for Storage Browser that do not use conditional writes.
 *
 * Every upload and every folder creation failed against the FSx for ONTAP S3
 * access point with HTTP 501:
 *
 *     PUT /<key>?x-id=PutObject
 *     if-none-match: *
 *     501 NotImplemented
 *     <Message>A header you provided implies functionality that is not implemented</Message>
 *
 * `if-none-match: *` is what `@aws-amplify/ui-react-storage` sends for its
 * `preventOverwrite` option, which its upload and createFolder handlers set from
 * the "Overwrite existing files" checkbox. S3 calls this a conditional write;
 * this access point does not implement it. The header is inside the SigV4
 * `SignedHeaders`, so it cannot be stripped after signing, and the handler is
 * the only seam `createStorageBrowser` offers.
 *
 * Measured, not assumed: a PUT carrying `x-amz-checksum-crc32` and no
 * `if-none-match` returns 200, and a PUT carrying `if-none-match: *` and no
 * checksum returns 501. The checksum the vendor sends is therefore fine and is
 * left in place; only the conditional write is replaced.
 *
 * Reads were never affected, because GET and ListObjectsV2 send neither header.
 * That is why browsing worked while every write failed.
 *
 * The replacement is a lookup before the write. It is not atomic the way
 * `if-none-match` is: two clients writing the same key at the same moment can
 * both see it as absent, and the later write wins. The alternative on this
 * endpoint is no overwrite protection at all.
 */
import { list, uploadData } from "@aws-amplify/storage/internals";
import { isCancelError } from "aws-amplify/storage";
import type {
  CreateFolderHandlerInput,
  CreateFolderHandlerOutput,
  UploadHandlerInput,
  UploadHandlerOutput,
} from "@aws-amplify/ui-react-storage/browser";

/** Matches the vendor threshold: above 5 MiB Amplify switches to multipart. */
const MULTIPART_UPLOAD_THRESHOLD_BYTES = 5 * 1024 * 1024;

/** Vendor default, kept because this endpoint accepts it (see the note above). */
const CHECKSUM_ALGORITHM = "crc-32" as const;

type ProgressEvent = { totalBytes?: number; transferredBytes: number };

type HandlerConfig = UploadHandlerInput["config"];

const ratio = ({ totalBytes, transferredBytes }: ProgressEvent): number | undefined =>
  totalBytes ? transferredBytes / totalBytes : undefined;

/** The handler's `config.bucket` is the S3 AP alias, used as the bucket name. */
const bucketOf = (config: HandlerConfig) => ({
  bucketName: config.bucket,
  region: config.region,
});

const sharedOptions = (config: HandlerConfig) => ({
  bucket: bucketOf(config),
  expectedBucketOwner: config.accountId,
  locationCredentialsProvider: config.credentials,
  customEndpoint: config.customEndpoint,
  checksumAlgorithm: CHECKSUM_ALGORITHM,
});

/**
 * Whether `key` already exists, by listing that exact prefix.
 *
 * A failed lookup returns false rather than blocking the write: refusing an
 * upload because a list call failed would report an overwrite that was never
 * established.
 */
const exists = async (config: HandlerConfig, key: string): Promise<boolean> => {
  try {
    const { items } = await list({
      path: key,
      options: {
        bucket: bucketOf(config),
        expectedBucketOwner: config.accountId,
        locationCredentialsProvider: config.credentials,
        customEndpoint: config.customEndpoint,
        pageSize: 1,
      },
    });
    return items.some((item) => item.path === key);
  } catch {
    return false;
  }
};

/**
 * `OVERWRITE_PREVENTED` in the shape the vendor views expect, so the UI reports
 * a blocked overwrite the same way it did when S3 refused the conditional write.
 */
const overwritePrevented = (key: string) => ({
  error: new Error(`${key} already exists`),
  message: `${key} already exists`,
  status: "OVERWRITE_PREVENTED" as const,
});

export const uploadWithoutConditionalWrite = ({
  config,
  data,
  options,
}: UploadHandlerInput): UploadHandlerOutput => {
  const { key, file, preventOverwrite } = data;
  const onProgress = options?.onProgress;

  const guard = preventOverwrite ? exists(config, key) : Promise.resolve(false);

  // `uploadData` has to be called synchronously to expose cancel/pause/resume,
  // so the guard is applied by racing it: the upload starts, and if the key
  // turns out to exist it is cancelled before the result is reported.
  const { cancel, pause, resume, result } = uploadData({
    path: key,
    data: file,
    options: {
      ...sharedOptions(config),
      onProgress: (event) => onProgress?.(data, ratio(event)),
    },
  });

  const guarded: UploadHandlerOutput["result"] = guard.then(async (found) => {
    if (found) {
      cancel();
      return overwritePrevented(key);
    }
    try {
      const output = await result;
      return { status: "COMPLETE" as const, value: { key: output.path } };
    } catch (caught) {
      const error = caught as Error;
      return {
        error,
        message: error.message,
        status: isCancelError(error) ? ("CANCELED" as const) : ("FAILED" as const),
      };
    }
  });

  // Pause and resume only exist for multipart uploads; offering them for a
  // single PutObject would render controls that cannot do anything.
  const controls =
    file.size > MULTIPART_UPLOAD_THRESHOLD_BYTES
      ? { cancel, pause, resume }
      : { cancel: undefined, pause: undefined, resume: undefined };

  return { ...controls, result: guarded };
};

export const createFolderWithoutConditionalWrite = ({
  config,
  data,
  options,
}: CreateFolderHandlerInput): CreateFolderHandlerOutput => {
  const { key, preventOverwrite } = data;
  const onProgress = options?.onProgress;

  const result: CreateFolderHandlerOutput["result"] = (async () => {
    if (preventOverwrite && (await exists(config, key))) {
      return overwritePrevented(key);
    }
    try {
      const { path } = await uploadData({
        path: key,
        data: "",
        options: {
          ...sharedOptions(config),
          onProgress: (event) => onProgress?.(data, ratio(event)),
        },
      }).result;
      return { status: "COMPLETE" as const, value: { key: path } };
    } catch (caught) {
      const error = caught as Error;
      return { error, message: error.message, status: "FAILED" as const };
    }
  })();

  return { result };
};
