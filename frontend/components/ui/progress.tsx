import { cn } from '@/lib/utils'

function Progress({
  value,
  className,
  barClassName,
  ...props
}: React.ComponentProps<'div'> & { value: number; barClassName?: string }) {
  const clamped = Math.min(100, Math.max(0, value))
  return (
    <div
      data-slot="progress"
      role="progressbar"
      aria-valuenow={clamped}
      aria-valuemin={0}
      aria-valuemax={100}
      className={cn('h-2 w-full overflow-hidden rounded-full bg-muted', className)}
      {...props}
    >
      <div
        className={cn('h-full rounded-full bg-primary transition-all duration-500', barClassName)}
        style={{ width: `${clamped}%` }}
      />
    </div>
  )
}

export { Progress }
