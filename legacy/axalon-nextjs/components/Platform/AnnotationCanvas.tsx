'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError, type Correction, type CorrectionCreate } from '@/lib/api'
import { queryKeys } from '@/lib/queryKeys'
import { useToast } from '@/components/Platform/Toast'
import { isTooSmall, normalizeBox, yoloToCanvas } from '@/components/Platform/canvasCoords'

export const CANONICAL_CLASSES = [
  'cell',
  'cell-multi',
  'module',
  'string',
  'bypass-diode',
  'offline-module',
  'vegetation-shading',
  'soiling',
  'short-circuit',
  'hot-spot-low',
  'hot-spot-high',
] as const

const SEVERITY_FOR_CLASS: Record<string, string> = {
  cell: 'MEDIUM',
  'cell-multi': 'MEDIUM',
  module: 'MEDIUM',
  string: 'CRITICAL',
  'bypass-diode': 'CRITICAL',
  'offline-module': 'HIGH',
  'vegetation-shading': 'LOW',
  soiling: 'LOW',
  'short-circuit': 'HIGH',
  'hot-spot-low': 'HIGH',
  'hot-spot-high': 'CRITICAL',
}

type YoloBox = {
  x1: number
  y1: number
  x2: number
  y2: number
  class_: string
  severity: string
  confidence: number
}

type LocalBox = {
  id: string
  serverId?: number
  x1n: number
  y1n: number
  x2n: number
  y2n: number
  class_: string
  class_id: number
  severity: string
}

function boxFromCorrection(c: Correction): LocalBox {
  return {
    id: String(c.id),
    serverId: c.id,
    x1n: c.bbox_norm[0],
    y1n: c.bbox_norm[1],
    x2n: c.bbox_norm[2],
    y2n: c.bbox_norm[3],
    class_: c.class,
    class_id: c.class_id ?? 0,
    severity: c.severity ?? 'MEDIUM',
  }
}

type Drawing = { x0: number; y0: number; x1: number; y1: number }

type Props = {
  jobId: string
  imageFile: File
  natW: number
  natH: number
  yoloBoxes: YoloBox[]
}

export function AnnotationCanvas({ jobId, imageFile, natW, natH, yoloBoxes }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const imgRef = useRef<HTMLImageElement | null>(null)
  const toast = useToast()

  const [boxes, setBoxes] = useState<LocalBox[]>([])
  const [drawing, setDrawing] = useState<Drawing | null>(null)
  const drawingRef = useRef<Drawing | null>(null)
  const [picker, setPicker] = useState<{ id: string; class_: string } | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const [, setImageVersion] = useState(0)
  const queryClient = useQueryClient()

  function setDrawingBoth(value: Drawing | null) {
    drawingRef.current = value
    setDrawing(value)
  }

  useEffect(() => {
    const url = URL.createObjectURL(imageFile)
    const img = new Image()
    img.onload = () => {
      imgRef.current = img
      setImageVersion((version) => version + 1)
    }
    img.src = url
    return () => URL.revokeObjectURL(url)
  }, [imageFile])

  // Older servers may not have corrections yet; drawing can still work locally.
  const correctionsQuery = useQuery({
    queryKey: queryKeys.jobs.corrections(jobId),
    queryFn: () => api.corrections(jobId),
    retry: false,
  })

  // Seed the editable boxes from the server once per job. Later refetches
  // (after a save/delete) must not wipe a box the user is still classifying.
  const seededJobRef = useRef<string | null>(null)
  useEffect(() => {
    if (!correctionsQuery.data || seededJobRef.current === jobId) return
    seededJobRef.current = jobId
    setBoxes(correctionsQuery.data.map(boxFromCorrection))
  }, [correctionsQuery.data, jobId])

  const refreshCorrections = () =>
    void queryClient.invalidateQueries({ queryKey: queryKeys.jobs.corrections(jobId) })

  const addMutation = useMutation({
    mutationFn: (body: CorrectionCreate) => api.addCorrection(jobId, body),
    onSuccess: refreshCorrections,
  })

  const deleteMutation = useMutation({
    mutationFn: (serverId: number) => api.deleteCorrection(jobId, serverId),
    onSuccess: refreshCorrections,
  })

  const sizeCanvas = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return null
    const width = canvas.offsetWidth || 640
    const height = Math.max(1, Math.round(width * (natH / Math.max(natW, 1))))
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width
      canvas.height = height
    }
    return { width, height }
  }, [natH, natW])

  const redraw = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const size = sizeCanvas()
    if (!size) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const cw = size.width
    const ch = size.height
    const img = imgRef.current
    if (img) {
      ctx.drawImage(img, 0, 0, cw, ch)
    } else {
      ctx.fillStyle = '#0f172a'
      ctx.fillRect(0, 0, cw, ch)
    }

    ctx.font = '600 11px Inter, system-ui, sans-serif'
    for (const box of yoloBoxes) {
      const { x1c, y1c, x2c, y2c } = yoloToCanvas(
        box.x1,
        box.y1,
        box.x2,
        box.y2,
        natW,
        natH,
        cw,
        ch,
      )
      ctx.strokeStyle = '#3b82f6'
      ctx.lineWidth = 2
      ctx.strokeRect(x1c, y1c, x2c - x1c, y2c - y1c)
      ctx.fillStyle = 'rgba(59, 130, 246, 0.12)'
      ctx.fillRect(x1c, y1c, x2c - x1c, y2c - y1c)
      ctx.fillStyle = '#bfdbfe'
      ctx.fillText(`${box.class_} ${Math.round(box.confidence * 100)}%`, x1c + 3, Math.max(12, y1c - 4))
    }

    for (const box of boxes) {
      const x1c = box.x1n * cw
      const y1c = box.y1n * ch
      const x2c = box.x2n * cw
      const y2c = box.y2n * ch
      const isSelected = box.id === selected
      ctx.strokeStyle = isSelected ? '#ecfccb' : '#22c55e'
      ctx.lineWidth = isSelected ? 3 : 2
      ctx.strokeRect(x1c, y1c, x2c - x1c, y2c - y1c)
      ctx.fillStyle = 'rgba(34, 197, 94, 0.12)'
      ctx.fillRect(x1c, y1c, x2c - x1c, y2c - y1c)
      ctx.fillStyle = '#bbf7d0'
      ctx.fillText(box.class_, x1c + 3, Math.max(12, y1c - 4))
    }

    if (drawing) {
      const { x0, y0, x1, y1 } = drawing
      ctx.strokeStyle = '#f59e0b'
      ctx.lineWidth = 2
      ctx.setLineDash([5, 4])
      ctx.strokeRect(x0, y0, x1 - x0, y1 - y0)
      ctx.setLineDash([])
    }
  }, [boxes, drawing, natH, natW, selected, sizeCanvas, yoloBoxes])

  useEffect(() => {
    redraw()
    window.addEventListener('resize', redraw)
    return () => window.removeEventListener('resize', redraw)
  }, [redraw])

  function point(e: React.MouseEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current
    if (!canvas) return { x: 0, y: 0 }
    const rect = canvas.getBoundingClientRect()
    return {
      x: ((e.clientX - rect.left) / rect.width) * canvas.width,
      y: ((e.clientY - rect.top) / rect.height) * canvas.height,
    }
  }

  function hitTest(x: number, y: number): LocalBox | undefined {
    const canvas = canvasRef.current
    if (!canvas) return undefined
    return [...boxes].reverse().find((box) => {
      const x1 = box.x1n * canvas.width
      const y1 = box.y1n * canvas.height
      const x2 = box.x2n * canvas.width
      const y2 = box.y2n * canvas.height
      return x >= x1 && x <= x2 && y >= y1 && y <= y2
    })
  }

  function onMouseDown(e: React.MouseEvent<HTMLCanvasElement>) {
    const { x, y } = point(e)
    const hit = hitTest(x, y)
    if (hit) {
      setSelected(hit.id)
      setPicker(null)
      setDrawingBoth(null)
      return
    }
    setDrawingBoth({ x0: x, y0: y, x1: x, y1: y })
    setSelected(null)
    setPicker(null)
  }

  function onMouseMove(e: React.MouseEvent<HTMLCanvasElement>) {
    if (!drawingRef.current) return
    const { x, y } = point(e)
    setDrawingBoth({ ...drawingRef.current, x1: x, y1: y })
  }

  function onMouseUp() {
    const d = drawingRef.current
    if (!d) return
    const canvas = canvasRef.current
    if (!canvas) return
    const norm = normalizeBox(d.x0, d.y0, d.x1, d.y1, canvas.width, canvas.height)
    setDrawingBoth(null)
    if (isTooSmall(norm.x1n, norm.y1n, norm.x2n, norm.y2n)) return
    const id = Math.random().toString(36).slice(2)
    setBoxes((current) => [...current, { id, ...norm, class_: 'cell', class_id: 0, severity: 'MEDIUM' }])
    setSelected(id)
    setPicker({ id, class_: 'cell' })
  }

  async function saveCorrection(id: string, class_: string) {
    const classId = CANONICAL_CLASSES.indexOf(class_ as (typeof CANONICAL_CLASSES)[number])
    const class_id = classId >= 0 ? classId : 0
    const severity = SEVERITY_FOR_CLASS[class_] ?? 'MEDIUM'
    const box = boxes.find((candidate) => candidate.id === id)
    if (!box) return
    setBoxes((current) =>
      current.map((candidate) =>
        candidate.id === id ? { ...candidate, class_, class_id, severity } : candidate,
      ),
    )
    setPicker(null)
    try {
      const saved = await addMutation.mutateAsync({
        class_,
        class_id,
        severity,
        bbox_norm: [box.x1n, box.y1n, box.x2n, box.y2n],
      })
      setBoxes((current) =>
        current.map((candidate) =>
          candidate.id === id ? { ...candidate, serverId: saved.id } : candidate,
        ),
      )
      toast.success('Correction saved')
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Failed to save correction')
    }
  }

  async function deleteSelected() {
    const box = boxes.find((candidate) => candidate.id === selected)
    if (!box) return
    if (box.serverId) {
      try {
        await deleteMutation.mutateAsync(box.serverId)
      } catch (err) {
        toast.error(err instanceof ApiError ? err.message : 'Failed to delete correction')
        return
      }
    }
    setBoxes((current) => current.filter((candidate) => candidate.id !== selected))
    setSelected(null)
  }

  return (
    <div style={{ position: 'relative', marginTop: 14 }}>
      <canvas
        ref={canvasRef}
        style={{
          width: '100%',
          aspectRatio: `${natW} / ${natH}`,
          display: 'block',
          cursor: 'crosshair',
          borderRadius: 8,
          background: '#0f172a',
        }}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={() => setDrawingBoth(null)}
      />

      {picker && (
        <div
          className="annotation-class-picker"
          style={{
            position: 'absolute',
            top: 8,
            right: 8,
            zIndex: 10,
            minWidth: 210,
            padding: 12,
            border: '1px solid #cbd5e1',
            borderRadius: 8,
            background: '#fff',
            boxShadow: '0 10px 24px rgba(15, 23, 42, 0.18)',
          }}
        >
          <div style={{ marginBottom: 8, fontSize: 12, fontWeight: 700 }}>Assign class</div>
          <select
            value={picker.class_}
            onChange={(e) => setPicker((current) => (current ? { ...current, class_: e.target.value } : null))}
            style={{ width: '100%', marginBottom: 8 }}
          >
            {CANONICAL_CLASSES.map((className) => (
              <option key={className} value={className}>
                {className}
              </option>
            ))}
          </select>
          <button
            className="primary"
            style={{ height: 30, marginTop: 0, fontSize: 12 }}
            onClick={() => saveCorrection(picker.id, picker.class_)}
          >
            Save
          </button>
          <button
            style={{
              height: 30,
              marginLeft: 6,
              padding: '0 10px',
              border: '1px solid #cbd5e1',
              borderRadius: 6,
              background: '#fff',
              cursor: 'pointer',
              fontSize: 12,
            }}
            onClick={() => {
              setBoxes((current) => current.filter((box) => box.id !== picker.id))
              setPicker(null)
              setSelected(null)
            }}
          >
            Cancel
          </button>
        </div>
      )}

      {selected && !picker && (
        <button
          style={{
            position: 'absolute',
            top: 8,
            right: 8,
            padding: '4px 10px',
            border: '1px solid #fecaca',
            borderRadius: 6,
            background: '#fee2e2',
            color: '#991b1b',
            cursor: 'pointer',
            fontSize: 12,
            fontWeight: 700,
          }}
          onClick={deleteSelected}
        >
          Delete
        </button>
      )}
    </div>
  )
}
