'use client'

import { CSSProperties } from 'react'

const shimmer: CSSProperties = {
  background: 'linear-gradient(90deg, #e2e8f0 25%, #f1f5f9 50%, #e2e8f0 75%)',
  backgroundSize: '200% 100%',
  animation: 'ax-shimmer 1.4s ease infinite',
  borderRadius: 6,
}

export function SkeletonLine({ width = '100%', height = 14 }: { width?: string | number; height?: number }) {
  return (
    <div
      style={{
        ...shimmer,
        width,
        height,
        borderRadius: 4,
      }}
    />
  )
}

export function SkeletonBlock({ height = 200, width = '100%' }: { height?: number; width?: string | number }) {
  return (
    <div
      style={{
        ...shimmer,
        width,
        height,
        borderRadius: 8,
      }}
    />
  )
}

export function SkeletonCircle({ size = 40 }: { size?: number }) {
  return (
    <div
      style={{
        ...shimmer,
        width: size,
        height: size,
        borderRadius: '50%',
        flexShrink: 0,
      }}
    />
  )
}

export function SkeletonStyle() {
  return (
    <style>{`
      @keyframes ax-shimmer {
        0%   { background-position: 200% 0; }
        100% { background-position: -200% 0; }
      }
    `}</style>
  )
}
