'use client'

import dynamic from 'next/dynamic'

const PlatformScene = dynamic(() => import('./PlatformScene'), {
  ssr: false,
  loading: () => (
    <div
      style={{
        width: '100%',
        height: '100%',
        background: '#02030a',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#00f0c8',
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: 12,
        letterSpacing: '0.18em',
      }}
    >
      INITIALIZING INSPECTION SCENE...
    </div>
  ),
})

export default PlatformScene
