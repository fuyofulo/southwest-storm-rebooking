// Small line icons (1.5px strokes, currentColor).

const base = { width: 16, height: 16, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.6, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true }

export const ChevronLeft = () => (
  <svg {...base}>
    <path d="M15 18l-6-6 6-6" />
  </svg>
)

export const ChevronRight = () => (
  <svg {...base}>
    <path d="M9 18l6-6-6-6" />
  </svg>
)

export const Search = () => (
  <svg {...base}>
    <circle cx="11" cy="11" r="7" />
    <path d="M20 20l-3.5-3.5" />
  </svg>
)

export const Refresh = () => (
  <svg {...base}>
    <path d="M20 11a8 8 0 1 0-2.3 5.7" />
    <path d="M20 4v7h-7" />
  </svg>
)

export const Sun = () => (
  <svg {...base}>
    <circle cx="12" cy="12" r="4" />
    <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
  </svg>
)

export const Moon = () => (
  <svg {...base}>
    <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" />
  </svg>
)

export const Check = () => (
  <svg {...base} width={14} height={14}>
    <path d="M5 12.5l4.5 4.5L19 7.5" />
  </svg>
)
