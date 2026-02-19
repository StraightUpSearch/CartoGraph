import { useQuery } from "@tanstack/react-query"
import { createFileRoute, Link } from "@tanstack/react-router"
import { Database, Globe, Zap } from "lucide-react"

import { DomainsService } from "@/client/cartograph"
import { StatCard } from "@/components/Common/StatCard"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import useAuth from "@/hooks/useAuth"

export const Route = createFileRoute("/_layout/")({
  component: Dashboard,
  head: () => ({
    meta: [{ title: "Dashboard — CartoGraph" }],
  }),
})

function Dashboard() {
  const { user: currentUser } = useAuth()

  const { data: stats, isLoading } = useQuery({
    queryKey: ["domain-stats"],
    queryFn: () => DomainsService.getDomainStats(),
  })

  return (
    <div className="space-y-8 p-1">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">
          Welcome back, {currentUser?.full_name ?? currentUser?.email}
        </h1>
        <p className="mt-1 text-muted-foreground">
          UK ecommerce domain intelligence — continuously updated.
        </p>
      </div>

      {/* Stats row */}
      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          title="Total Domains"
          value={stats?.total_domains}
          icon={Database}
          description="Validated UK ecommerce stores"
          loading={isLoading}
        />
        <StatCard
          title="Active Domains"
          value={stats?.active_domains}
          icon={Globe}
          description="Currently monitored and enriched"
          loading={isLoading}
        />
        <StatCard
          title="New This Week"
          value={stats?.new_this_week}
          icon={Zap}
          description="Discovered in the last 7 days"
          loading={isLoading}
        />
      </div>

      {/* Quick actions */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold">Browse Domains</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <p className="text-sm text-muted-foreground">
              Filter by platform, DR, traffic, intent score and more.
            </p>
            <Button asChild size="sm" className="w-full">
              <Link to="/domains">Open Domain Database</Link>
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold">Alerts</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <p className="text-sm text-muted-foreground">
              Get notified when domains gain SERP features, change tech stack,
              or spike in traffic.
            </p>
            <Button asChild size="sm" variant="outline" className="w-full">
              <Link to="/alerts">Manage Alerts</Link>
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold">
              Workspace &amp; API
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <p className="text-sm text-muted-foreground">
              Manage your workspace, rotate API tokens, and view usage quotas.
            </p>
            <Button asChild size="sm" variant="outline" className="w-full">
              <Link to="/workspaces">Open Workspace</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
