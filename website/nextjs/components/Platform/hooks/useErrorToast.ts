'use client'

import { useEffect } from 'react'
import { useToast } from '@/components/Platform/Toast'

function defaultMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

/**
 * Toast once per failure. react-query keeps the same error object until the
 * next attempt fails, so keying the effect on it never repeats a toast for a
 * failure the user has already seen.
 */
export function useErrorToast(error: unknown, format: (err: unknown) => string = defaultMessage): void {
  const toast = useToast()
  useEffect(() => {
    if (error) toast.error(format(error))
  }, [error]) // eslint-disable-line react-hooks/exhaustive-deps
}
