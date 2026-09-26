/// <reference types="vite/client" />

/**
 * The only environment variable the interface reads.
 *
 * It is left unset in both normal deployments: in development Vite proxies /v1 to the API, and in
 * production FastAPI serves this bundle from the same origin. Set it only when the two are split
 * across hosts.
 */
interface ImportMetaEnv {
  readonly VITE_API_BASE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
