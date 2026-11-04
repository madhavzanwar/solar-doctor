'use client'

import { useCallback, useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { queryKeys } from '@/lib/queryKeys'
import { useToast } from '@/components/Platform/Toast'

export type SettingsBlob = Record<string, Record<string, unknown>>

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

/** Normalize: API may return { settings: blob } or blob directly. */
function normalizeSettings(raw: unknown): SettingsBlob {
  if (raw && typeof raw === 'object' && 'settings' in raw) {
    return (raw as { settings: SettingsBlob }).settings
  }
  return raw as SettingsBlob
}

/**
 * settings.yaml editor state. The server copy lives in the query cache; edits
 * go into a local draft that shadows it until saved or reloaded.
 */
export function useSettings(): {
  settings: SettingsBlob | null
  loading: boolean
  dirty: boolean
  message: string
  update: (group: string, key: string, value: unknown) => void
  save: () => Promise<void>
  load: () => void
} {
  const toast = useToast()
  const queryClient = useQueryClient()
  const [draft, setDraft] = useState<SettingsBlob | null>(null)
  const [message, setMessage] = useState('')

  const query = useQuery({
    queryKey: queryKeys.settings.blob,
    queryFn: async () => normalizeSettings(await api.getSettings()),
  })
  const { refetch } = query

  useEffect(() => {
    if (!query.error) return
    const msg = errorMessage(query.error)
    setMessage(msg)
    toast.error(msg)
  }, [query.error]) // eslint-disable-line react-hooks/exhaustive-deps

  const settings = draft ?? query.data ?? null

  const load = useCallback(() => {
    setMessage('')
    setDraft(null)
    void refetch()
  }, [refetch])

  const update = useCallback(
    (group: string, key: string, value: unknown) => {
      setDraft((prev) => {
        const base = prev ?? queryClient.getQueryData<SettingsBlob>(queryKeys.settings.blob)
        if (!base) return prev
        return {
          ...base,
          [group]: {
            ...(base[group] ?? {}),
            [key]: value,
          },
        }
      })
    },
    [queryClient],
  )

  const mutation = useMutation({
    mutationFn: (blob: SettingsBlob) => api.putSettings(blob as Record<string, unknown>),
    onSuccess: (_res, saved) => {
      // What we sent is now the server state; show it until the refetch lands.
      queryClient.setQueryData(queryKeys.settings.blob, saved)
      setDraft(null)
      setMessage('Saved · platform restart may be required for some fields')
      void queryClient.invalidateQueries({ queryKey: queryKeys.settings.blob })
    },
    onError: (err) => {
      const msg = errorMessage(err)
      setMessage(msg)
      toast.error(msg)
    },
  })
  const { mutateAsync } = mutation

  const save = useCallback(async () => {
    if (!settings) return
    setMessage('')
    await mutateAsync(settings).catch(() => undefined)
  }, [settings, mutateAsync])

  return {
    settings,
    loading: query.isFetching,
    dirty: draft !== null,
    message,
    update,
    save,
    load,
  }
}
