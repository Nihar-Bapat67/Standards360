import { Link } from 'react-router-dom'

/** The mark: a plumb line over a base, which is what a standard is. */
export function Wordmark({ small = false, to = '/' }: { small?: boolean; to?: string }) {
  const size = small ? 26 : 30

  return (
    <Link to={to} className="group flex items-center gap-2.5" aria-label="Standards360 home">
      <span
        className="flex shrink-0 items-center justify-center rounded-[9px] transition-transform duration-500 ease-[cubic-bezier(0.16,1,0.3,1)] group-hover:scale-105"
        style={{
          width: size,
          height: size,
          background: 'linear-gradient(145deg,#FF8A5B 0%,#FF5F7A 55%,#E95D9C 100%)',
        }}
      >
        <svg
          width={size * 0.55}
          height={size * 0.55}
          viewBox="0 0 24 24"
          fill="none"
          stroke="#0A0508"
          strokeWidth="2.4"
          strokeLinecap="round"
          aria-hidden
        >
          <path d="M12 3v18M6 8h12M8 21h8" />
        </svg>
      </span>
      <span className={`font-semibold tracking-[-0.02em] ${small ? 'text-[14px]' : 'text-[16px]'}`}>
        Standards<span className="text-amber">360</span>
      </span>
    </Link>
  )
}
