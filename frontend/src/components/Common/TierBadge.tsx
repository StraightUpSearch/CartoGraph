import { Badge } from "@/components/ui/badge"

const TIER_COLORS: Record<
  string,
  "default" | "secondary" | "destructive" | "outline"
> = {
  free: "outline",
  starter: "secondary",
  professional: "default",
  business: "default",
  enterprise: "default",
}

const TIER_LABELS: Record<string, string> = {
  free: "Free",
  starter: "Starter",
  professional: "Pro",
  business: "Business",
  enterprise: "Enterprise",
}

interface TierBadgeProps {
  tier: string
  showLabel?: boolean
}

export function TierBadge({ tier, showLabel = true }: TierBadgeProps) {
  const variant = TIER_COLORS[tier] ?? "outline"
  const label = TIER_LABELS[tier] ?? tier

  return (
    <Badge variant={variant} className="text-xs uppercase tracking-wider">
      {showLabel ? label : tier}
    </Badge>
  )
}
