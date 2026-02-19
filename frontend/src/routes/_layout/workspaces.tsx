/**
 * /workspaces — workspace settings, API token management, usage quotas.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute, Link } from "@tanstack/react-router"
import { Copy, CreditCard, ExternalLink, Globe, RotateCcw } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"

import { BillingService, WorkspacesService, type WorkspacePublic } from "@/client/cartograph"
import { TierBadge } from "@/components/Common/TierBadge"
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

export const Route = createFileRoute("/_layout/workspaces")({
  component: WorkspacesPage,
  head: () => ({
    meta: [{ title: "Workspaces — CartoGraph" }],
  }),
})

function UsageBar({
  used,
  limit,
  label,
}: {
  used: number
  limit: number | null
  label: string
}) {
  const pct = limit != null ? Math.min((used / limit) * 100, 100) : 0
  const color =
    pct > 90 ? "bg-destructive" : pct > 70 ? "bg-yellow-500" : "bg-primary"

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>{label}</span>
        <span>
          {used.toLocaleString()}
          {limit != null ? ` / ${limit.toLocaleString()}` : " / ∞"}
        </span>
      </div>
      {limit != null && (
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
          <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Billing card
// ---------------------------------------------------------------------------

const TIER_LABELS: Record<string, string> = {
  free: "Free",
  starter: "Starter — £39/mo",
  professional: "Professional — £119/mo",
  business: "Business — £279/mo",
  enterprise: "Enterprise",
}

function BillingCard({ workspace }: { workspace: WorkspacePublic }) {
  const portalMutation = useMutation({
    mutationFn: () => BillingService.getBillingPortal(),
    onSuccess: (data) => {
      window.location.href = data.url
    },
    onError: () => toast.error("Failed to open billing portal"),
  })

  const hasSubscription = !!workspace.stripe_subscription_status
  const statusColour =
    workspace.stripe_subscription_status === "active"
      ? "text-green-600 dark:text-green-400"
      : workspace.stripe_subscription_status === "past_due"
        ? "text-red-600 dark:text-red-400"
        : "text-muted-foreground"

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Subscription</CardTitle>
        <CardDescription>
          {TIER_LABELS[workspace.tier] ?? workspace.tier}
          {workspace.stripe_subscription_status && (
            <span className={`ml-2 text-xs font-medium capitalize ${statusColour}`}>
              ({workspace.stripe_subscription_status.replace("_", " ")})
            </span>
          )}
        </CardDescription>
      </CardHeader>
      <CardFooter className="flex flex-wrap gap-2">
        {hasSubscription ? (
          <Button
            variant="outline"
            size="sm"
            onClick={() => portalMutation.mutate()}
            disabled={portalMutation.isPending}
          >
            <CreditCard className="mr-1.5 h-4 w-4" />
            {portalMutation.isPending ? "Opening…" : "Manage subscription"}
            <ExternalLink className="ml-1.5 h-3 w-3 opacity-60" />
          </Button>
        ) : null}
        <Button variant="default" size="sm" asChild>
          <Link to="/pricing">
            {workspace.tier === "free" ? "Upgrade plan" : "Change plan"}
          </Link>
        </Button>
      </CardFooter>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Workspace card
// ---------------------------------------------------------------------------

function WorkspaceCard({ workspace }: { workspace: WorkspacePublic }) {
  const queryClient = useQueryClient()
  const [newToken, setNewToken] = useState<string | null>(null)

  const { data: usage, isLoading: usageLoading } = useQuery({
    queryKey: ["workspace-usage", workspace.workspace_id],
    queryFn: () =>
      WorkspacesService.getWorkspaceUsage(workspace.workspace_id),
  })

  const rotateMutation = useMutation({
    mutationFn: () =>
      WorkspacesService.rotateToken(workspace.workspace_id),
    onSuccess: (data) => {
      setNewToken(data.token)
      queryClient.invalidateQueries({
        queryKey: ["workspaces"],
      })
      toast.warning(
        "New API token generated. Copy it now — it won't be shown again.",
        { duration: 8000 },
      )
    },
    onError: () => toast.error("Failed to rotate token"),
  })

  const copyToken = () => {
    if (!newToken) return
    navigator.clipboard.writeText(newToken)
    toast.success("Token copied to clipboard")
  }

  return (
    <div className="space-y-4">
      {/* Identity */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">{workspace.name}</CardTitle>
            <TierBadge tier={workspace.tier} />
          </div>
          <CardDescription>
            Created{" "}
            {new Date(workspace.created_at).toLocaleDateString("en-GB", {
              day: "numeric",
              month: "long",
              year: "numeric",
            })}
          </CardDescription>
        </CardHeader>
      </Card>

      {/* Usage quotas */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Monthly Usage</CardTitle>
          <CardDescription>
            Resets on{" "}
            {usage?.billing_cycle_start
              ? new Date(usage.billing_cycle_start).toLocaleDateString(
                  "en-GB",
                  { day: "numeric", month: "long" },
                )
              : "—"}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {usageLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-full" />
            </div>
          ) : usage ? (
            <div className="space-y-4">
              <UsageBar
                used={usage.domain_lookups.used}
                limit={usage.domain_lookups.limit}
                label="Domain Lookups"
              />
              <UsageBar
                used={usage.export_credits.used}
                limit={usage.export_credits.limit}
                label="Export Credits"
              />
              <UsageBar
                used={usage.api_calls.used}
                limit={usage.api_calls.limit}
                label="API Calls"
              />
            </div>
          ) : null}
        </CardContent>
      </Card>

      {/* Billing */}
      <BillingCard workspace={workspace} />

      {/* API token */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">API Token</CardTitle>
          <CardDescription>
            Use this token for workspace-scoped API access. Pass it as{" "}
            <code className="rounded bg-muted px-1 py-0.5 text-xs">
              Authorization: Bearer &lt;token&gt;
            </code>
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {newToken ? (
            <div className="flex items-center gap-2 rounded-md bg-muted p-3">
              <code className="flex-1 break-all text-xs">{newToken}</code>
              <Button
                variant="ghost"
                size="sm"
                onClick={copyToken}
                title="Copy token"
              >
                <Copy className="h-4 w-4" />
              </Button>
            </div>
          ) : workspace.api_token_prefix ? (
            <div className="rounded-md bg-muted p-3">
              <code className="text-xs text-muted-foreground">
                {workspace.api_token_prefix}••••••••••••••••••••••
              </code>
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">
              No token generated yet.
            </p>
          )}

          <Button
            variant="outline"
            size="sm"
            onClick={() => rotateMutation.mutate()}
            disabled={rotateMutation.isPending}
          >
            <RotateCcw className="mr-1.5 h-4 w-4" />
            {workspace.api_token_prefix ? "Rotate Token" : "Generate Token"}
          </Button>

          {newToken && (
            <p className="text-xs text-amber-600 dark:text-amber-400">
              ⚠ This token won't be shown again. Copy it now.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function WorkspacesPage() {
  const { data: workspaces, isLoading } = useQuery({
    queryKey: ["workspaces"],
    queryFn: () => WorkspacesService.listWorkspaces(),
  })

  return (
    <div className="space-y-6 p-1">
      <div className="flex items-start gap-3">
        <Globe className="mt-0.5 h-5 w-5 text-muted-foreground" />
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Workspaces</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Manage your workspace tier, API tokens, and monthly usage quotas.
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      ) : workspaces && workspaces.length > 0 ? (
        <div className="max-w-2xl">
          <WorkspaceCard workspace={workspaces[0]} />
        </div>
      ) : (
        <div className="rounded-lg border border-dashed p-12 text-center">
          <Globe className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
          <p className="mb-1 text-sm font-medium">No workspace yet</p>
          <p className="text-xs text-muted-foreground">
            A workspace will be created automatically on first API use.
          </p>
        </div>
      )}
    </div>
  )
}
