import { Badge, type badgeVariants } from '@/components/ui/badge'
import type { VariantProps } from 'class-variance-authority'

type BadgeVariant = VariantProps<typeof badgeVariants>['variant']

interface StatusConfig {
  label: string
  variant: BadgeVariant
}

const CANDIDATE_STATUS: Record<string, StatusConfig> = {
  interested: { label: 'Interested', variant: 'success' },
  selected: { label: 'Selected', variant: 'success' },
  hired: { label: 'Hired', variant: 'success' },
  pending: { label: 'Pending', variant: 'warning' },
  callback: { label: 'Callback', variant: 'warning' },
  calling: { label: 'Calling', variant: 'warning' },
  interview: { label: 'Interview', variant: 'info' },
  interview_completed: { label: 'Interview Completed', variant: 'info' },
  rejected: { label: 'Rejected', variant: 'destructive' },
  cancelled: { label: 'Cancelled', variant: 'destructive' },
}

const INTERVIEW_STATUS: Record<string, StatusConfig> = {
  invited: { label: 'Invited', variant: 'info' },
  scheduled: { label: 'Scheduled', variant: 'info' },
  in_progress: { label: 'In Progress', variant: 'warning' },
  completed: { label: 'Completed', variant: 'success' },
  cancelled: { label: 'Cancelled', variant: 'destructive' },
  expired: { label: 'Expired', variant: 'destructive' },
  failed: { label: 'Failed', variant: 'destructive' },
}

const RECOMMENDATION_STATUS: Record<string, StatusConfig> = {
  strong_match: { label: 'Strong Match', variant: 'success' },
  match: { label: 'Match', variant: 'success' },
  weak_match: { label: 'Weak Match', variant: 'warning' },
  no_match: { label: 'No Match', variant: 'destructive' },
}

const CAMPAIGN_STATUS: Record<string, StatusConfig> = {
  pending: { label: 'Pending', variant: 'warning' },
  calling: { label: 'Calling', variant: 'warning' },
  completed: { label: 'Completed', variant: 'success' },
  failed: { label: 'Failed', variant: 'destructive' },
}

const DOMAINS = {
  candidate: CANDIDATE_STATUS,
  interview: INTERVIEW_STATUS,
  recommendation: RECOMMENDATION_STATUS,
  campaign: CAMPAIGN_STATUS,
} as const

interface StatusPillProps {
  domain: keyof typeof DOMAINS
  status: string
  label?: string
}

function StatusPill({ domain, status, label }: StatusPillProps) {
  const config = DOMAINS[domain][status] ?? { label: label ?? status, variant: 'neutral' as BadgeVariant }
  return <Badge variant={config.variant}>{label ?? config.label}</Badge>
}

export { StatusPill }
