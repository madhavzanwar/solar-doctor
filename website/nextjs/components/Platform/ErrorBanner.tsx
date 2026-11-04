'use client'

import { AlertTriangle, RotateCw } from 'lucide-react'

type ErrorBannerProps = {
  message: string
  onRetry?: () => void
}

export function ErrorBanner({ message, onRetry }: ErrorBannerProps) {
  return (
    <div className="ax-error-banner" role="alert">
      <AlertTriangle size={15} className="ax-error-banner-icon" />
      <span className="ax-error-banner-msg">{message}</span>
      {onRetry && (
        <button type="button" className="ax-error-banner-retry" onClick={onRetry}>
          <RotateCw size={13} /> Retry
        </button>
      )}
    </div>
  )
}
