import type { ReactNode, CSSProperties } from 'react'

type BtnVariant = 'primary' | 'discover' | 'ghost' | 'save' | 'saveActive'

interface BtnProps {
  children: ReactNode
  onClick?: () => void
  variant?: BtnVariant
  icon?: ReactNode
  disabled?: boolean
}

const variantStyles: Record<BtnVariant, CSSProperties> = {
  primary: {
    background: 'var(--accent)',
    color: '#fff',
    fontWeight: 600,
    border: 'none',
  },
  discover: {
    background: 'var(--badge-discover)',
    color: '#fff',
    fontWeight: 600,
    border: 'none',
  },
  ghost: {
    background: 'transparent',
    color: 'var(--text-3)',
    border: '1px solid var(--border)',
  },
  save: {
    background: 'var(--save-bg)',
    color: 'var(--text-2)',
    border: 'none',
  },
  saveActive: {
    background: 'var(--accent-soft)',
    color: 'var(--save-active)',
    fontWeight: 600,
    border: 'none',
  },
}

export default function Btn({ children, onClick, variant = 'ghost', icon, disabled }: BtnProps) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="inline-flex items-center justify-center gap-1.5 px-3.5 rounded-[10px] text-xs cursor-pointer transition-opacity hover:opacity-85 disabled:opacity-50 disabled:cursor-default"
      style={{
        fontFamily: 'inherit',
        fontWeight: 500,
        lineHeight: '20px',
        paddingTop: 7,
        paddingBottom: 7,
        ...variantStyles[variant],
      }}
    >
      {icon}
      {children}
    </button>
  )
}
