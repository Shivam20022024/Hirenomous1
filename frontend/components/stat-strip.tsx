import { cn } from '@/lib/utils'

interface StatStripItem {
  value: React.ReactNode
  label: string
}

function StatStrip({ items, className }: { items: StatStripItem[]; className?: string }) {
  return (
    <div
      className={cn(
        'grid grid-cols-2 gap-6 rounded-xl border border-border bg-card px-6 py-5 sm:grid-cols-4',
        className,
      )}
    >
      {items.map((item, index) => (
        <div key={index} className="flex flex-col items-center gap-1 text-center sm:items-start sm:text-left">
          <span className="font-mono text-2xl font-bold text-foreground sm:text-3xl">{item.value}</span>
          <span className="text-xs font-medium text-muted-foreground">{item.label}</span>
        </div>
      ))}
    </div>
  )
}

export { StatStrip }
