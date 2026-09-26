/**
 * The ground every screen sits on: near-black, a technical grid, and warm radial light.
 *
 * It lives in one component so the ambient palette cannot drift between pages, and so the rule that
 * keeps this looking like an engineering product rather than a neon site — light stays under 20%
 * opacity and moves slowly if at all — is enforced in a single place.
 */

interface AtmosphereProps {
  /** `hero` is the landing page's full warm wash; `work` is the restrained version for the app. */
  variant?: 'hero' | 'work'
}

export function Atmosphere({ variant = 'hero' }: AtmosphereProps) {
  const hero = variant === 'hero'

  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden bg-ink-0">
      <div className={hero ? 'absolute inset-0 grid-ground' : 'absolute inset-0 grid-ground-flat opacity-60'} />

      {/* Warm light from the upper left, the anchor of the whole palette. */}
      <div
        className={`ambient ${hero ? 'h-[46rem] w-[46rem]' : 'h-[32rem] w-[32rem]'}`}
        style={{
          top: hero ? '-18rem' : '-16rem',
          left: hero ? '-14rem' : '-12rem',
          background:
            'radial-gradient(circle, rgb(255 138 91 / 0.16) 0%, rgb(255 110 100 / 0.09) 30%, rgb(255 95 122 / 0.04) 55%, transparent 76%)',
        }}
      />

      {/* Pink counterweight, lower right, so the frame is lit diagonally rather than evenly. */}
      <div
        className={`ambient ${hero ? 'h-[40rem] w-[40rem]' : 'h-[26rem] w-[26rem]'}`}
        style={{
          bottom: '-16rem',
          right: '-12rem',
          background:
            'radial-gradient(circle, rgb(233 93 156 / 0.13) 0%, rgb(233 93 156 / 0.06) 32%, rgb(255 95 122 / 0.03) 56%, transparent 76%)',
        }}
      />

      {/* One cold accent, kept faint. It exists to stop the warm light reading as a single wash. */}
      {hero && (
        <div
          className="ambient h-[30rem] w-[30rem]"
          style={{
            top: '38%',
            right: '18%',
            background: 'radial-gradient(circle, rgb(91 140 255 / 0.07) 0%, rgb(91 140 255 / 0.03) 38%, transparent 72%)',
          }}
        />
      )}

      {/* A vignette that settles everything back into the ground at the edges. */}
      <div
        className="absolute inset-0"
        style={{
          background:
            'radial-gradient(ellipse 120% 80% at 50% 0%, transparent 40%, rgb(5 5 7 / 0.55) 100%)',
        }}
      />
    </div>
  )
}
