/**
 * /domains/$domainId — full domain profile page.
 *
 * Displays all enrichment data in a tabbed layout. Fields are masked
 * according to the user's workspace tier (handled by the backend;
 * _gated flags on JSONB groups drive frontend upgrade prompts).
 */

import { useQuery } from "@tanstack/react-query"
import { createFileRoute, Link } from "@tanstack/react-router"
import { ArrowLeft, ExternalLink, RefreshCw } from "lucide-react"
import { Suspense } from "react"

import { DomainsService } from "@/client/cartograph"
import { DomainProfileTabs } from "@/components/Domains/DomainProfileTabs"
import { TierBadge } from "@/components/Common/TierBadge"
import { WorkspacesService } from "@/client/cartograph"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"

export const Route = createFileRoute("/_layout/domains/$domainId")({
  component: DomainProfilePage,
  head: () => ({
    meta: [{ title: "Domain Profile — CartoGraph" }],
  }),
})

function DomainProfilePage() {
  const { domainId } = Route.useParams()

  const { data: domain, isLoading, error } = useQuery({
    queryKey: ["domain", domainId],
    queryFn: () => DomainsService.getDomain(domainId),
  })

  const { data: workspaces } = useQuery({
    queryKey: ["workspaces"],
    queryFn: () => WorkspacesService.listWorkspaces(),
  })

  const tier = workspaces?.[0]?.tier ?? "free"

  if (isLoading) {
    return (
      <div className="space-y-6 p-1">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-[500px] w-full" />
      </div>
    )
  }

  if (error || !domain) {
    return (
      <div className="p-1">
        <p className="text-sm text-destructive">
          Domain not found or you don't have access.
        </p>
        <Button asChild variant="link" className="mt-2 px-0">
          <Link to="/domains">Back to database</Link>
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-6 p-1">
      {/* Back link */}
      <Button asChild variant="ghost" size="sm" className="-ml-2">
        <Link to="/domains">
          <ArrowLeft className="mr-1.5 h-4 w-4" />
          Domain Database
        </Link>
      </Button>

      {/* Domain header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight">
              {domain.domain}
            </h1>
            <a
              href={`https://${domain.domain}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-muted-foreground hover:text-foreground transition-colors"
              title="Open website"
            >
              <ExternalLink className="h-5 w-5" />
            </a>
          </div>
          <div className="mt-1.5 flex items-center gap-2 text-sm text-muted-foreground">
            <span>{domain.country}</span>
            <span>·</span>
            <span className="capitalize">{domain.status}</span>
            <span>·</span>
            <TierBadge tier={tier} />
          </div>
        </div>

        <Button variant="outline" size="sm" className="shrink-0" disabled>
          <RefreshCw className="mr-1.5 h-4 w-4" />
          Re-enrich
        </Button>
      </div>

      {/* Tab content */}
      <DomainProfileTabs domain={domain} tier={tier} />
    </div>
  )
}
