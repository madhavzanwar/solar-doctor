'use client'

import { useRef, Suspense } from 'react'
import { Canvas } from '@react-three/fiber'
import { EffectComposer, Bloom, Vignette } from '@react-three/postprocessing'
import { Stars } from '@react-three/drei'
import SolarField from './SolarField'
import Drone from './Drone'
import CameraRig from './CameraRig'
import SceneController from './SceneController'
import ThermalScan from './ThermalScan'
import DetectionBoxes from './DetectionBoxes'
import DroneFleet from './DroneFleet'
import HologramPanel from './HologramPanel'
import CTAEffect from './CTAEffect'
import type { SolarFieldHandle } from './SolarField'

export default function MainScene() {
  const fieldRef = useRef<SolarFieldHandle>(null)

  return (
    <div style={{
      width: '100%',
      height: '100%',
      background: '#020208',
    }}>
      <Canvas
        camera={{ position: [0, 18, 28], fov: 60, near: 0.1, far: 300 }}
        gl={{
          antialias: true,
          alpha: false,
          powerPreference: 'high-performance',
        }}
        shadows
        dpr={[1, 1.5]}
      >
        <Suspense fallback={null}>

          {/* ── Atmosphere ── */}
          <fog attach="fog" args={['#020208', 35, 90]} />
          <color attach="background" args={['#020208']} />

          {/* ── Base lighting ── */}
          <ambientLight intensity={0.15} color="#0a0a2a" />
          <directionalLight
            position={[12, 22, 12]}
            intensity={0.4}
            color="#c8d4f0"
            castShadow
            shadow-mapSize={[1024, 1024]}
            shadow-camera-near={1}
            shadow-camera-far={80}
            shadow-camera-left={-30}
            shadow-camera-right={30}
            shadow-camera-top={30}
            shadow-camera-bottom={-30}
          />
          <pointLight position={[0, -5, 0]} color="#002a25" intensity={0.6} distance={50} />

          {/* ── Starfield ── */}
          <Stars
            radius={120}
            depth={50}
            count={3000}
            factor={3}
            saturation={0}
            fade
            speed={0.2}
          />

          {/* ── Scene 1: solar field + hero drone ── */}
          <SolarField ref={fieldRef} />
          <Drone position={[0, 4.5, -2]} phase={0} lightIntensity={5} />

          {/* ── Scene 2: thermal scan + scanning drone ── */}
          <ThermalScan />

          {/* ── Scene 3: RGB + AI detection boxes ── */}
          <DetectionBoxes />

          {/* ── Scene 4: autonomous drone fleet ── */}
          <DroneFleet />

          {/* ── Scene 5: holographic inspection report ── */}
          <HologramPanel />

          {/* ── Scene 6: CTA particle effect ── */}
          <CTAEffect />

          {/* ── Orchestration ── */}
          <SceneController fieldRef={fieldRef} />
          <CameraRig />


          {/* ── Post processing ── */}
          <EffectComposer>
            <Bloom
              luminanceThreshold={0.18}
              luminanceSmoothing={0.3}
              intensity={1.8}
            />
            <Vignette darkness={0.55} offset={0.25} />
          </EffectComposer>

        </Suspense>
      </Canvas>
    </div>
  )
}
