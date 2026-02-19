import { Lock, Zap } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

const TIER_ORDER = ["free", "starter", "professional", "business", "enterprise"]
const TIER_PRICES: Record<string, string> = {
  starter: "£39/mo",
  professional: "£119/mo",
  business: "£279/mo",
  enterprise: "£749+/mo",
}

interface UpgradeModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  currentTier: string
  requiredTier: string
  featureName: string
}

export function UpgradeModal({
  open,
  onOpenChange,
  currentTier,
  requiredTier,
  featureName,
}: UpgradeModalProps) {
  const upgradePath = TIER_ORDER.slice(
    TIER_ORDER.indexOf(currentTier) + 1,
    TIER_ORDER.indexOf(requiredTier) + 1,
  )

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <div className="mb-2 flex h-12 w-12 items-center justify-center rounded-full bg-muted">
            <Lock className="h-6 w-6 text-muted-foreground" />
          </div>
          <DialogTitle>Upgrade to access {featureName}</DialogTitle>
          <DialogDescription>
            This feature is available on the{" "}
            <strong className="capitalize">{requiredTier}</strong> plan and above.
            {TIER_PRICES[requiredTier] && (
              <> Starting at {TIER_PRICES[requiredTier]}.</>
            )}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">
          {upgradePath.map((tier) => (
            <div
              key={tier}
              className="flex items-center gap-3 rounded-lg border p-3"
            >
              <Zap className="h-4 w-4 text-primary" />
              <div>
                <p className="text-sm font-medium capitalize">{tier}</p>
                {TIER_PRICES[tier] && (
                  <p className="text-xs text-muted-foreground">
                    {TIER_PRICES[tier]}
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>

        <div className="flex gap-2">
          <Button variant="outline" onClick={() => onOpenChange(false)} className="flex-1">
            Cancel
          </Button>
          <Button className="flex-1" asChild>
            <a href="/settings#billing">Upgrade Plan</a>
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}

/** Small inline gated field indicator — replaces masked field values. */
export function GatedField({
  tier,
  feature,
}: {
  tier: string
  feature: string
}) {
  return (
    <span
      className="inline-flex cursor-default items-center gap-1 rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground"
      title={`Upgrade to ${feature} to see this data`}
    >
      <Lock className="h-3 w-3" />
      {tier} feature
    </span>
  )
}
