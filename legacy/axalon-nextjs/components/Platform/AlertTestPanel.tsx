'use client'

import { BellRing, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { api, type AlertChannelStatus, type AlertTestResult } from '@/lib/api'

const CHANNEL_LABELS = { webhook: 'Webhook', email: 'Email' } as const

const STATUS_TONE: Record<AlertChannelStatus, 'ok' | 'crit' | 'muted'> = {
  sent: 'ok',
  failed: 'crit',
  skipped: 'muted',
  not_configured: 'muted',
}

function statusLabel(status: AlertChannelStatus): string {
  return status.replace('_', ' ')
}

/** Settings panel: fire a test alert through every configured channel. */
export function AlertTestPanel() {
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<AlertTestResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const sendTest = async () => {
    setBusy(true)
    setError(null)
    try {
      setResult(await api.testAlert())
    } catch (err) {
      setResult(null)
      setError(err instanceof Error ? err.message : 'Test alert request failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <div className="panel-title">Fault alerts</div>
          <p>
            Webhook and email notifications for new faults. Channels are configured with
            AXALON_ALERT_* / AXALON_SMTP_* environment variables on the API server.
          </p>
        </div>
        <button type="button" className="secondary" disabled={busy} onClick={sendTest}>
          {busy ? <RefreshCw size={15} /> : <BellRing size={15} />}
          Send test alert
        </button>
      </div>

      {error && (
        <div className="note error" role="alert">
          {error}
        </div>
      )}

      {result && (
        <div className="settings-fields" aria-live="polite">
          {!result.configured && (
            <p className="save-msg">No alert channels are configured on the server.</p>
          )}
          <p className="save-msg">Alerts fire for faults at or above {result.min_severity}.</p>
          <div className="chips">
            {(Object.keys(CHANNEL_LABELS) as (keyof typeof CHANNEL_LABELS)[]).map((key) => {
              const channel = result.channels[key]
              if (!channel) return null
              return (
                <div key={key} className={`chip chip-${STATUS_TONE[channel.status] ?? 'muted'}`}>
                  <span className="chip-label">{CHANNEL_LABELS[key]}</span>
                  <span className="chip-value">{statusLabel(channel.status)}</span>
                  {channel.detail && <span className="chip-label"> · {channel.detail}</span>}
                </div>
              )
            })}
          </div>
        </div>
      )}
    </section>
  )
}
