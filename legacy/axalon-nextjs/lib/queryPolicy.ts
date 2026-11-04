import { ApiError } from '@/lib/api'

/**
 * Errors that will not fix themselves by asking again: missing credentials,
 * forbidden, or a resource that does not exist. Polling queries stop on these
 * so a revoked session or deleted job doesn't fire a request (and an
 * `axalon:unauthorized` event) every tick.
 */
export function isTerminalHttpError(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 401 || error.status === 403 || error.status === 404)
}
