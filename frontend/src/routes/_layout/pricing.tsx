/**
 * /pricing — public-facing pricing page with tier comparison table.
 *
 * Fetches the live plan catalogue from the backend (includes founding member seat count).
 * Logged-in users can click "Upgrade" to start a Stripe Checkout session.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { Check, Crown, Sparkles, Zap } from "lucide-react"
import { toast } from "sonner"

import { BillingService, type Plan, type WorkspacePublic } from "@/client/cartograph"
import { WorkspacesService } from "@/client/cartograph"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import useAuth from "@/hooks/useAuth"

export const Route = createFileRoute("/_layout/pricing")({
  component: PricingPage,
  head: () => ({
    meta: [{ title: "Pricing — CartoGraph" }],
  }),
})

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatPrice(gbp: number | null): string {
  if (gbp === null) return "Custom"
  if (gbp === 0) return "Free"
  return `£${gbp}`
}

const TIER_ORDER = ["free", "starter", "professional", "business", "enterprise"]

function tierIndex(tier: string): number {
  return TIER_ORDER.indexOf(tier)
}

// ---------------------------------------------------------------------------
// FoundingMemberBanner
// ---------------------------------------------------------------------------

function FoundingMemberBanner({
  available,
  cap,
}: {
  available: number
  cap: number
}) {
  if (available <= 0) return null
  return (
    <div className="flex items-center gap-3 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 dark:border-amber-700 dark:bg-amber-950">
      <Crown className="h-5 w-5 shrink-0 text-amber-600 dark:text-amber-400" />
      <div className="text-sm">
        <span className="font-semibold text-amber-800 dark:text-amber-300">
          Founding Member programme open —{" "}
        </span>
        <span className="text-amber-700 dark:text-amber-400">
          {available} of {cap} seats remaining. Lock in 50% off Professional for life.
        </span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// PlanCard
// ---------------------------------------------------------------------------

function PlanCard({
  plan,
  currentTier,
  isAnnual,
  foundingAvailable,
  onUpgrade,
  isLoading,
}: {
  plan: Plan
  currentTier: string | null
  isAnnual: boolean
  foundingAvailable: boolean
  onUpgrade: (priceId: string) => void
  isLoading: boolean
}) {
  const isCurrent = plan.tier === currentTier
  const isUpgrade =
    currentTier !== null && tierIndex(plan.tier) > tierIndex(currentTier)
  const isDowngrade =
    currentTier !== null && tierIndex(plan.tier) < tierIndex(currentTier)
  const isFree = plan.tier === "free"
  const isEnterprise = plan.tier === "enterprise"

  const showFounding =
    plan.founding_member &&
    foundingAvailable &&
    isAnnual &&
    plan.tier === "professional"

  const displayPrice = showFounding
    ? plan.founding_member!.price_annual_gbp
    : isAnnual
      ? plan.price_annual_gbp
      : plan.price_monthly_gbp

  const priceId = showFounding
    ? plan.founding_member!.stripe_price_id
    : isAnnual
      ? plan.stripe_price_annual
      : plan.stripe_price_monthly

  const buttonLabel = isCurrent
    ? "Current plan"
    : isFree
      ? "Downgrade to Free"
      : isDowngrade
        ? "Downgrade"
        : isUpgrade
          ? "Upgrade"
          : "Get started"

  const highlighted = plan.tier === "professional"

  return (
    <Card
      className={`relative flex flex-col ${highlighted ? "border-primary shadow-md" : ""}`}
    >
      {highlighted && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2">
          <Badge className="bg-primary text-primary-foreground px-3 py-0.5 text-xs">
            Most popular
          </Badge>
        </div>
      )}
      {showFounding && (
        <div className="absolute -top-3 right-4">
          <Badge
            variant="outline"
            className="border-amber-400 bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300 px-2 py-0.5 text-xs"
          >
            <Crown className="mr-1 h-3 w-3" />
            Founding
          </Badge>
        </div>
      )}

      <CardHeader className="pb-4">
        <CardTitle className="text-lg">{plan.name}</CardTitle>
        <CardDescription className="text-sm">{plan.description}</CardDescription>
        <div className="mt-3 flex items-end gap-1">
          <span className="text-3xl font-bold tracking-tight">
            {formatPrice(displayPrice)}
          </span>
          {displayPrice !== null && displayPrice > 0 && (
            <span className="mb-1 text-sm text-muted-foreground">
              /{isAnnual ? "mo, billed annually" : "mo"}
            </span>
          )}
        </div>
        {showFounding && (
          <p className="text-xs text-amber-700 dark:text-amber-400">
            was £{plan.price_annual_gbp}/mo — 50% off for life
          </p>
        )}
      </CardHeader>

      <CardContent className="flex-1">
        <ul className="space-y-2">
          {plan.highlights.map((h) => (
            <li key={h} className="flex items-start gap-2 text-sm">
              <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
              <span>{h}</span>
            </li>
          ))}
        </ul>
      </CardContent>

      <CardFooter>
        {isEnterprise ? (
          <Button
            variant="outline"
            className="w-full"
            onClick={() =>
              window.open("mailto:hello@cartograph.com?subject=Enterprise enquiry", "_blank")
            }
          >
            Contact sales
          </Button>
        ) : isFree ? (
          <Button
            variant="outline"
            className="w-full"
            disabled={isCurrent}
          >
            {isCurrent ? "Current plan" : "Free forever"}
          </Button>
        ) : (
          <Button
            className="w-full"
            variant={highlighted ? "default" : "outline"}
            disabled={isCurrent || isLoading || !priceId}
            onClick={() => priceId && onUpgrade(priceId)}
          >
            {isLoading ? "Redirecting…" : buttonLabel}
          </Button>
        )}
      </CardFooter>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// PricingPage
// ---------------------------------------------------------------------------

function PricingPage() {
  const { user } = useAuth()
  const isLoggedIn = !!user
  const [isAnnual, setIsAnnual] = React.useState(true)

  const { data: plansData, isLoading: plansLoading } = useQuery({
    queryKey: ["billing-plans"],
    queryFn: () => BillingService.getPlans(),
    staleTime: 60_000,
  })

  const { data: workspaces } = useQuery({
    queryKey: ["workspaces"],
    queryFn: () => WorkspacesService.listWorkspaces(),
    enabled: isLoggedIn,
  })

  const currentTier = workspaces?.[0]?.tier ?? null

  const checkoutMutation = useMutation({
    mutationFn: (priceId: string) => BillingService.startCheckout(priceId),
    onSuccess: (data) => {
      window.location.href = data.url
    },
    onError: (err: Error) => {
      toast.error(err.message || "Failed to start checkout. Please try again.")
    },
  })

  return (
    <div className="space-y-8 p-1">
      {/* Header */}
      <div className="text-center">
        <div className="mb-2 flex items-center justify-center gap-2">
          <Sparkles className="h-5 w-5 text-primary" />
          <h1 className="text-3xl font-bold tracking-tight">Pricing</h1>
        </div>
        <p className="mx-auto max-w-xl text-sm text-muted-foreground">
          UK ecommerce intelligence for every team size. Upgrade or downgrade at any time.
          All prices in GBP.
        </p>
      </div>

      {/* Annual / Monthly toggle */}
      <div className="flex items-center justify-center gap-3">
        <span
          className={`text-sm ${!isAnnual ? "font-semibold" : "text-muted-foreground"}`}
        >
          Monthly
        </span>
        <button
          type="button"
          role="switch"
          aria-checked={isAnnual}
          onClick={() => setIsAnnual((v) => !v)}
          className={`relative inline-flex h-6 w-11 cursor-pointer rounded-full border-2 border-transparent transition-colors focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 ${isAnnual ? "bg-primary" : "bg-muted"}`}
        >
          <span
            className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition-transform ${isAnnual ? "translate-x-5" : "translate-x-0"}`}
          />
        </button>
        <span
          className={`flex items-center gap-1.5 text-sm ${isAnnual ? "font-semibold" : "text-muted-foreground"}`}
        >
          Annual
          <Badge variant="secondary" className="text-xs">
            Save ~17%
          </Badge>
        </span>
      </div>

      {/* Founding member banner */}
      {plansData && plansData.founding_member.available > 0 && (
        <FoundingMemberBanner
          available={plansData.founding_member.available}
          cap={plansData.founding_member.cap}
        />
      )}

      {/* Plan grid */}
      {plansLoading ? (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-96 w-full rounded-xl" />
          ))}
        </div>
      ) : plansData ? (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
          {plansData.plans.map((plan) => (
            <PlanCard
              key={plan.tier}
              plan={plan}
              currentTier={currentTier}
              isAnnual={isAnnual}
              foundingAvailable={plansData.founding_member.available > 0}
              onUpgrade={(priceId) => {
                if (!isLoggedIn) {
                  window.location.href = "/login"
                  return
                }
                checkoutMutation.mutate(priceId)
              }}
              isLoading={checkoutMutation.isPending}
            />
          ))}
        </div>
      ) : null}

      {/* FAQ / footnote */}
      <div className="rounded-lg border bg-muted/30 p-6">
        <div className="flex items-start gap-3">
          <Zap className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
          <div className="space-y-1 text-sm text-muted-foreground">
            <p>
              <strong className="text-foreground">Instant activation.</strong>{" "}
              Your tier unlocks immediately after payment — no waiting for manual approval.
            </p>
            <p>
              <strong className="text-foreground">Monthly usage resets</strong> on
              your billing anniversary date each month.
            </p>
            <p>
              <strong className="text-foreground">Need help choosing?</strong>{" "}
              Email{" "}
              <a
                href="mailto:hello@cartograph.com"
                className="underline underline-offset-2"
              >
                hello@cartograph.com
              </a>{" "}
              and we'll help you pick the right plan.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}

// React import needed for useState
import * as React from "react"
