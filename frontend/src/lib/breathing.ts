/** Cyclic sighing: two inhales through the nose (the second one short, to top up), then one long
 * exhale through the mouth. The circle grows on the inhales and shrinks on the exhale. */
export const PHASES = [
  { key: 'inhale', cue: 'Inhale through your nose', seconds: 2, from: 0.55, to: 0.85, tone: [196, 233] },
  { key: 'top', cue: 'Again, a little more', seconds: 1, from: 0.85, to: 1, tone: [233, 262] },
  { key: 'exhale', cue: 'Long, slow exhale through your mouth', seconds: 6, from: 1, to: 0.55, tone: [220, 165] },
] as const

export const CYCLE_SECONDS = PHASES.reduce((n, p) => n + p.seconds, 0)

export function phaseAt(elapsed: number): { index: number; progress: number; scale: number; cycle: number } {
  const cycle = Math.floor(elapsed / CYCLE_SECONDS)
  let t = elapsed - cycle * CYCLE_SECONDS
  for (let index = 0; index < PHASES.length; index++) {
    const p = PHASES[index]
    if (t < p.seconds) {
      const progress = t / p.seconds
      const eased = 0.5 - Math.cos(progress * Math.PI) / 2 // soft in and out
      return { index, progress, scale: p.from + (p.to - p.from) * eased, cycle }
    }
    t -= p.seconds
  }
  return { index: 0, progress: 0, scale: PHASES[0].from, cycle: cycle + 1 }
}

/** A soft sine glide for one phase (WebAudio, no files); quiet by design. */
export function playTone(ctx: AudioContext, [from, to]: readonly number[], seconds: number) {
  const osc = ctx.createOscillator()
  const gain = ctx.createGain()
  const now = ctx.currentTime
  osc.type = 'sine'
  osc.frequency.setValueAtTime(from, now)
  osc.frequency.linearRampToValueAtTime(to, now + seconds)
  gain.gain.setValueAtTime(0, now)
  gain.gain.linearRampToValueAtTime(0.035, now + Math.min(0.4, seconds / 3))
  gain.gain.linearRampToValueAtTime(0, now + seconds)
  osc.connect(gain).connect(ctx.destination)
  osc.start(now)
  osc.stop(now + seconds + 0.05)
}
