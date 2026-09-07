import { cn } from '@/lib/utils'

interface StatTileProps {
  label: string
  value: React.ReactNode
  icon?: React.ReactNode
  tone?: 'primary' | 'success' | 'warning' | 'info' | 'neutral'
  hint?: string
  className?: string
}

const toneStyles: Record<NonNullable<StatTileProps['tone']>, string> = {
  primary: 'bg-primary/10 text-primary',
  success: 'bg-success/15 text-success',
  warning: 'bg-warning/20 text-warning-text',
  info: 'bg-accent/20 text-accent-foreground',
  neutral: 'bg-muted text-muted-foreground',
}

function StatTile({ label, value, icon, tone = 'neutral', hint, className }: StatTileProps) {
  return (
    <div
      className={cn(
        'flex flex-col gap-3 rounded-xl border border-border bg-card p-5 shadow-sm',
        className,
      )}
    >
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</span>
        {icon && (
          <span className={cn('flex h-8 w-8 items-center justify-center rounded-lg', toneStyles[tone])}>
            {icon}
          </span>
        )}
      </div>
      <span className="font-mono text-2xl font-bold text-foreground">{value}</span>
      {hint && <span className="text-xs text-muted-foreground">{hint}</span>}
    </div>
  )
}

export { StatTile }
