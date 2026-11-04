'use client'

import dynamic from 'next/dynamic'

const Scene3D = dynamic(() => import('./Scene3D'), { ssr: false })

export default function DynamicScene3D() {
  return <Scene3D />
}
