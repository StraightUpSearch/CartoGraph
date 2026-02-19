/**
 * /alerts — alert management page.
 *
 * Lists all saved alerts for the user's workspace with create/toggle/delete.
 * Alert count limits are enforced by the API (tier-dependent) and surfaced
 * via error toasts.
 */

import { createFileRoute } from "@tanstack/react-router"
import { Bell } from "lucide-react"

import { AlertsList } from "@/components/Alerts/AlertsList"

export const Route = createFileRoute("/_layout/alerts")({
  component: AlertsPage,
  head: () => ({
    meta: [{ title: "Alerts — CartoGraph" }],
  }),
})

function AlertsPage() {
  return (
    <div className="space-y-6 p-1">
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Bell className="h-5 w-5 text-muted-foreground" />
            <h1 className="text-2xl font-bold tracking-tight">Alerts</h1>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">
            Get notified when domain data changes — new domains, tech changes,
            DR shifts, or SERP feature wins.
          </p>
        </div>
      </div>

      <AlertsList />
    </div>
  )
}
