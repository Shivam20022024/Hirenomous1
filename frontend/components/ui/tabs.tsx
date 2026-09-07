import { cn } from '@/lib/utils'

function Tabs({ className, ...props }: React.ComponentProps<'div'>) {
  return <div data-slot="tabs" className={cn('flex flex-col gap-4', className)} {...props} />
}

function TabsList({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      data-slot="tabs-list"
      role="tablist"
      className={cn('inline-flex w-fit items-center gap-1 rounded-lg border border-border bg-muted p-1', className)}
      {...props}
    />
  )
}

function TabsTrigger({
  className,
  active,
  ...props
}: React.ComponentProps<'button'> & { active?: boolean }) {
  return (
    <button
      type="button"
      data-slot="tabs-trigger"
      role="tab"
      aria-selected={active}
      className={cn(
        'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
        active
          ? 'bg-card text-primary shadow-sm'
          : 'text-muted-foreground hover:text-foreground',
        className,
      )}
      {...props}
    />
  )
}

function TabsPanel({ className, ...props }: React.ComponentProps<'div'>) {
  return <div data-slot="tabs-panel" role="tabpanel" className={cn(className)} {...props} />
}

export { Tabs, TabsList, TabsTrigger, TabsPanel }
