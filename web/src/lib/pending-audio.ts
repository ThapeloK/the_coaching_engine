/**
 * Hold a recording that could not be sent, and send it when the signal comes
 * back.
 *
 * The mentor named this directly: "Offline availability could support quick
 * use in areas with unreliable connectivity." That is not a hypothetical in a
 * hotel. Service corridors, the laundry, the loading bay and most basements
 * are exactly where a duty manager is when they see something worth logging,
 * and they are exactly where the wifi is not.
 *
 * What matters is that the failure is invisible to the person. They talk, the
 * button says it saved, and they walk on. The upload happens when the building
 * lets it. The alternative, an error toast asking them to try again later,
 * means the observation is never logged, because nobody tries again later.
 *
 * IndexedDB rather than localStorage because this stores audio: localStorage
 * holds strings and caps out around five megabytes. The recordings never leave
 * the device except to reach our own transcription endpoint, and they are
 * deleted from here the moment one is accepted.
 */

const DB_NAME = "ce-pending-audio";
const STORE = "recordings";
const VERSION = 1;

export interface PendingRecording {
  id: number;
  blob: Blob;
  filename: string;
  recordedAt: number;
}

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: "id", autoIncrement: true });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

/** Every call is wrapped: a browser in private mode, or one told to block site
 * data, throws on open rather than returning an empty database. A manager
 * whose browser refuses to store this should still be able to record, so every
 * failure here degrades to "nothing is queued" and never to a broken page. */
async function withStore<T>(
  mode: IDBTransactionMode,
  run: (store: IDBObjectStore) => IDBRequest,
  fallback: T,
): Promise<T> {
  if (typeof indexedDB === "undefined") return fallback;
  try {
    const db = await open();
    return await new Promise<T>((resolve) => {
      const tx = db.transaction(STORE, mode);
      const request = run(tx.objectStore(STORE));
      request.onsuccess = () => resolve(request.result as T);
      request.onerror = () => resolve(fallback);
      tx.oncomplete = () => db.close();
    });
  } catch {
    return fallback;
  }
}

export async function queueRecording(
  blob: Blob,
  filename: string,
): Promise<void> {
  await withStore(
    "readwrite",
    (store) => store.add({ blob, filename, recordedAt: Date.now() }),
    undefined,
  );
}

export async function listPending(): Promise<PendingRecording[]> {
  const rows = await withStore<PendingRecording[]>(
    "readonly",
    (store) => store.getAll(),
    [],
  );
  return rows ?? [];
}

export async function dropRecording(id: number): Promise<void> {
  await withStore("readwrite", (store) => store.delete(id), undefined);
}

/** True when the browser is certain it has no connection. `navigator.onLine`
 * lies in the optimistic direction (it reports true for a wifi network with no
 * route out), so this is only ever used to explain a failure that already
 * happened, never to decide whether to try. */
export function definitelyOffline(): boolean {
  return typeof navigator !== "undefined" && navigator.onLine === false;
}
