import { useEffect, useRef } from 'react'

// Ported from initStarfield() in the legacy static/index.html. Deterministic
// star layout (seeded RNG) repainted on resize.
export default function Starfield() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const draw = () => {
      const w = canvas.width
      const h = canvas.height

      const bg = ctx.createLinearGradient(0, 0, 0, h)
      bg.addColorStop(0, '#05060d')
      bg.addColorStop(0.3, '#080c1a')
      bg.addColorStop(0.6, '#0a0f22')
      bg.addColorStop(1, '#05060d')
      ctx.fillStyle = bg
      ctx.fillRect(0, 0, w, h)

      const nebulae = [
        { x: w * 0.2, y: h * 0.3, r: Math.max(w, h) * 0.25, c: 'rgba(0,100,230,0.03)' },
        { x: w * 0.75, y: h * 0.15, r: Math.max(w, h) * 0.2, c: 'rgba(120,60,200,0.025)' },
        { x: w * 0.5, y: h * 0.75, r: Math.max(w, h) * 0.22, c: 'rgba(40,180,130,0.02)' },
        { x: w * 0.85, y: h * 0.7, r: Math.max(w, h) * 0.18, c: 'rgba(0,80,180,0.025)' },
      ]
      nebulae.forEach((n) => {
        const g = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, n.r)
        g.addColorStop(0, n.c)
        g.addColorStop(1, 'transparent')
        ctx.fillStyle = g
        ctx.fillRect(0, 0, w, h)
      })

      const rng = (seed: number) => () => {
        seed = (seed * 16807) % 2147483647
        return (seed - 1) / 2147483646
      }
      const rand = rng(42)
      for (let i = 0; i < 600; i++) {
        const x = rand() * w
        const y = rand() * h
        const sz = rand()
        const br = rand()
        let r: number, g: number, b: number
        if (br < 0.6) {
          r = 255
          g = 255
          b = 255
        } else if (br < 0.75) {
          r = 200
          g = 220
          b = 255
        } else if (br < 0.88) {
          r = 255
          g = 240
          b = 200
        } else {
          r = 180
          g = 200
          b = 255
        }
        const a = 0.15 + br * 0.65
        const radius = sz < 0.7 ? 0.5 : sz < 0.92 ? 0.8 : 1.2
        if (radius > 0.9) {
          ctx.beginPath()
          ctx.arc(x, y, radius * 3, 0, Math.PI * 2)
          ctx.fillStyle = `rgba(${r},${g},${b},${a * 0.08})`
          ctx.fill()
        }
        ctx.beginPath()
        ctx.arc(x, y, radius, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(${r},${g},${b},${a})`
        ctx.fill()
      }
      for (let j = 0; j < 15; j++) {
        const bx = rand() * w
        const by = rand() * h
        const bsz = 1.5 + rand() * 1.5
        const ba = 0.6 + rand() * 0.4
        const br2 = rng(100 + j * 37)
        const bcr = br2()
        const bcb = br2()
        let bgr: number, bgg: number, bgb: number
        if (bcr > 0.5) {
          bgr = 220
          bgg = 235
          bgb = 255
        } else if (bcb > 0.5) {
          bgr = 255
          bgg = 230
          bgb = 200
        } else {
          bgr = 200
          bgg = 210
          bgb = 255
        }
        ctx.beginPath()
        ctx.arc(bx, by, bsz * 4, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(${bgr},${bgg},${bgb},${ba * 0.12})`
        ctx.fill()
        ctx.beginPath()
        ctx.arc(bx, by, bsz, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(${bgr},${bgg},${bgb},${ba})`
        ctx.fill()
        const sp = bsz * 8
        ctx.strokeStyle = `rgba(${bgr},${bgg},${bgb},${ba * 0.15})`
        ctx.lineWidth = 0.5
        ctx.beginPath()
        ctx.moveTo(bx - sp, by)
        ctx.lineTo(bx + sp, by)
        ctx.stroke()
        ctx.beginPath()
        ctx.moveTo(bx, by - sp)
        ctx.lineTo(bx, by + sp)
        ctx.stroke()
      }
    }

    const resize = () => {
      canvas.width = window.innerWidth
      canvas.height = window.innerHeight
      draw()
    }

    window.addEventListener('resize', resize)
    resize()
    return () => window.removeEventListener('resize', resize)
  }, [])

  return (
    <div className="starfield">
      <canvas ref={canvasRef} />
    </div>
  )
}
