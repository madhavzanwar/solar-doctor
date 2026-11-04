'use client'

import dynamic from 'next/dynamic'
import type { OrthoMapProps } from './OrthoMap'

const OrthoMap = dynamic<OrthoMapProps>(() => import('./OrthoMap').then((m) => m.OrthoMap), {
  ssr: false,
  loading: () => (
    <div
      style={{
        height: 420,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#0f172a',
        borderRadius: 8,
        color: '#cbd5e1',
        fontSize: 13,
      }}
    >
      Loading map...
    </div>
  ),
})

export { OrthoMap as DynamicOrthoMap }
