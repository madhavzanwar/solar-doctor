import { z } from 'zod'

/**
 * Mirrors the server-side contract in
 * platform/api/support/security.py::_validate_park_id — 1–64 chars, letters,
 * digits, hyphen, underscore. Checked client-side so an invalid park ID fails
 * instantly instead of after a multi-GB ZIP finishes uploading.
 *
 * Keep in sync with the Python validator.
 */
export const parkIdSchema = z
  .string()
  .trim()
  .min(1, 'Park ID is required')
  .max(64, 'Park ID must be 64 characters or fewer')
  .regex(
    /^[a-zA-Z0-9_-]+$/,
    'Park ID may only contain letters, digits, hyphens, and underscores',
  )

/** Survey altitude in metres. Bounds are sanity limits, not a server constraint. */
export const altitudeSchema = z
  .number({ invalid_type_error: 'Altitude must be a number' })
  .positive('Altitude must be greater than 0')
  .max(1000, 'Altitude above 1000 m is outside the supported range')

export const batchUploadSchema = z.object({
  park_id: parkIdSchema,
  altitude_m: altitudeSchema,
  file_name: z
    .string()
    .refine((n) => n.toLowerCase().endsWith('.zip'), 'Only .zip mission folders can be submitted'),
})

export type BatchUploadValues = z.infer<typeof batchUploadSchema>

/** First validation message, or null when valid. */
export function firstError(result: z.SafeParseReturnType<unknown, unknown>): string | null {
  return result.success ? null : (result.error.issues[0]?.message ?? 'Invalid input')
}
