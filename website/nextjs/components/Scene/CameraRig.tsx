'use client'

import { useRef, useEffect } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import { scrollStore } from '../../scrollStore'

// ── Camera position waypoints (mapped to scroll 0→1) ──────────────────────
// Each entry = camera position at that scroll fraction
const CAM_POSITIONS = new THREE.CatmullRomCurve3([
  new THREE.Vector3(0,  18, 28),   // 0%  — Hero: angled overhead
  new THREE.Vector3(0,  32,  3),   // 20% — Thermal: top-down
  new THREE.Vector3(22, 16,  8),   // 40% — Detection: isometric
  new THREE.Vector3(0,  38, 38),   // 60% — Fleet: wide altitude
  new THREE.Vector3(7,   6, 18),   // 80% — Hologram: eye level
  new THREE.Vector3(0,  18, 28),   // 100% — CTA: back to hero
], false, 'catmullrom', 0.5)

// ── Camera look-at waypoints ───────────────────────────────────────────────
const CAM_TARGETS = new THREE.CatmullRomCurve3([
  new THREE.Vector3(0,   0, -3),   // Hero — look slightly into field
  new THREE.Vector3(0,   0,  0),   // Thermal — look straight down at center
  new THREE.Vector3(0,   2,  0),   // Detection — slight elevation
  new THREE.Vector3(0,   0,  0),   // Fleet — wide center
  new THREE.Vector3(3,   2,  0),   // Hologram — look at floating display
  new THREE.Vector3(0,   0, -3),   // CTA — back to hero look
], false, 'catmullrom', 0.5)

// Per-scene ambient light intensities
const AMBIENT_INTENSITIES = [0.15, 0.08, 0.35, 0.12, 0.2, 0.15]
const SCENE_FOG_NEAR     = [30, 25, 40, 20, 25, 30]
const SCENE_FOG_FAR      = [80, 70, 90, 60, 70, 80]

export default function CameraRig() {
  const { camera, scene } = useThree()
  const posTarget  = useRef(new THREE.Vector3(0, 18, 28))
  const lookTarget = useRef(new THREE.Vector3(0, 0, -3))
  const currentFov = useRef(60)

  // Set initial camera
  useEffect(() => {
    camera.position.set(0, 18, 28)
    camera.lookAt(0, 0, -3)
  }, [camera])

  useFrame((_, delta) => {
    const raw = Math.min(Math.max(scrollStore.progress, 0), 0.9999)

    // Smooth the scroll value for buttery camera movement
    // Use different lerp speeds for pos vs look
    const desiredPos  = CAM_POSITIONS.getPointAt(raw)
    const desiredLook = CAM_TARGETS.getPointAt(raw)

    posTarget.current.lerp(desiredPos,  Math.min(1, delta * 2.5))
    lookTarget.current.lerp(desiredLook, Math.min(1, delta * 3.0))

    camera.position.copy(posTarget.current)
    camera.lookAt(lookTarget.current)

    // Subtle FOV breathing per scene
    const section = Math.floor(raw * 6)
    const targetFov = section === 1 ? 45 : section === 3 ? 50 : 60
    currentFov.current += (targetFov - currentFov.current) * delta * 2
    ;(camera as THREE.PerspectiveCamera).fov = currentFov.current
    ;(camera as THREE.PerspectiveCamera).updateProjectionMatrix()
  })

  return null
}
