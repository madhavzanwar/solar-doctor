'use client'

import dynamic from 'next/dynamic'

const MainScene = dynamic(
  () => import('./Scene/MainScene'),
  { ssr: false }
)

export default function DynamicMainScene() {
  return <MainScene />
}
