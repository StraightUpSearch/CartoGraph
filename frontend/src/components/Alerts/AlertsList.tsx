/**
 * AlertsList — full CRUD for saved alert configurations.
 *
 * Uses the first workspace the user owns. If no workspace exists, prompts
 * to create one. Enforces per-tier alert count limits (shown via error toast).
 */

import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Bell,
  BellOff,
  Plus,
  Trash2,
} from "lucide-react"
import { useForm } from "react-hook-form"
import { toast } from "sonner"
import { z } from "zod"

import {
  AlertsService,
  WorkspacesService,
  type AlertCreate,
  type AlertPublic,
} from "@/client/cartograph"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"

const ALERT_TYPE_LABELS: Record<string, string> = {
  new_domain: "New Domain",
  tech_change: "Tech Change",
  dr_change: "DR Change",
  serp_feature: "SERP Feature",
}

const alertSchema = z.object({
  name: z.string().min(1, "Name is required").max(255),
  alert_type: z.enum(["new_domain", "tech_change", "dr_change", "serp_feature"]),
  threshold_dr_delta: z.coerce.number().optional(),
  threshold_traffic_delta: z.coerce.number().optional(),
})

type AlertFormValues = z.infer<typeof alertSchema>

function CreateAlertDialog({
  workspaceId,
  onCreated,
}: {
  workspaceId: string
  onCreated: () => void
}) {
  const form = useForm<AlertFormValues>({
    resolver: zodResolver(alertSchema),
    defaultValues: { alert_type: "new_domain" },
  })

  const mutation = useMutation({
    mutationFn: (values: AlertFormValues) => {
      const payload: AlertCreate = {
        name: values.name,
        alert_type: values.alert_type,
        threshold:
          values.threshold_dr_delta != null ||
          values.threshold_traffic_delta != null
            ? {
                dr_delta: values.threshold_dr_delta,
                traffic_delta: values.threshold_traffic_delta,
              }
            : undefined,
      }
      return AlertsService.createAlert(workspaceId, payload)
    },
    onSuccess: () => {
      toast.success("Alert created")
      form.reset()
      onCreated()
    },
    onError: (err: { body?: { detail?: string } }) => {
      toast.error(err?.body?.detail ?? "Failed to create alert")
    },
  })

  return (
    <Form {...form}>
      <form
        onSubmit={form.handleSubmit((v) => mutation.mutate(v))}
        className="space-y-4"
      >
        <FormField
          control={form.control}
          name="name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Alert Name</FormLabel>
              <FormControl>
                <Input {...field} placeholder="e.g. High-intent Shopify stores" />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="alert_type"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Alert Type</FormLabel>
              <Select onValueChange={field.onChange} defaultValue={field.value}>
                <FormControl>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {Object.entries(ALERT_TYPE_LABELS).map(([val, label]) => (
                    <SelectItem key={val} value={val}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />

        {(form.watch("alert_type") === "dr_change" ||
          form.watch("alert_type") === "tech_change") && (
          <FormField
            control={form.control}
            name="threshold_dr_delta"
            render={({ field }) => (
              <FormItem>
                <FormLabel>DR Change Threshold (points)</FormLabel>
                <FormControl>
                  <Input {...field} type="number" placeholder="e.g. 10" min={1} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        )}

        <Button
          type="submit"
          className="w-full"
          disabled={mutation.isPending}
        >
          {mutation.isPending ? "Creating…" : "Create Alert"}
        </Button>
      </form>
    </Form>
  )
}

function AlertRow({
  alert,
  workspaceId,
  onMutated,
}: {
  alert: AlertPublic
  workspaceId: string
  onMutated: () => void
}) {
  const toggleMutation = useMutation({
    mutationFn: () =>
      AlertsService.toggleAlert(workspaceId, alert.alert_id),
    onSuccess: () => {
      toast.success(alert.is_active ? "Alert paused" : "Alert activated")
      onMutated()
    },
    onError: () => toast.error("Failed to update alert"),
  })

  const deleteMutation = useMutation({
    mutationFn: () =>
      AlertsService.deleteAlert(workspaceId, alert.alert_id),
    onSuccess: () => {
      toast.success("Alert deleted")
      onMutated()
    },
    onError: () => toast.error("Failed to delete alert"),
  })

  return (
    <div className="flex items-center justify-between rounded-lg border p-3.5">
      <div className="flex items-center gap-3">
        <div
          className={`flex h-8 w-8 items-center justify-center rounded-full ${alert.is_active ? "bg-primary/10" : "bg-muted"}`}
        >
          {alert.is_active ? (
            <Bell className="h-4 w-4 text-primary" />
          ) : (
            <BellOff className="h-4 w-4 text-muted-foreground" />
          )}
        </div>
        <div>
          <p className="text-sm font-medium">{alert.name}</p>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="text-xs">
              {ALERT_TYPE_LABELS[alert.alert_type] ?? alert.alert_type}
            </Badge>
            {alert.last_triggered && (
              <span className="text-xs text-muted-foreground">
                Last fired:{" "}
                {new Date(alert.last_triggered).toLocaleDateString("en-GB", {
                  day: "numeric",
                  month: "short",
                })}
              </span>
            )}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-1">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => toggleMutation.mutate()}
          disabled={toggleMutation.isPending}
          title={alert.is_active ? "Pause alert" : "Activate alert"}
        >
          {alert.is_active ? (
            <BellOff className="h-4 w-4" />
          ) : (
            <Bell className="h-4 w-4" />
          )}
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => deleteMutation.mutate()}
          disabled={deleteMutation.isPending}
          className="text-destructive hover:text-destructive"
          title="Delete alert"
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}

export function AlertsList() {
  const queryClient = useQueryClient()

  const { data: workspaces, isLoading: wsLoading } = useQuery({
    queryKey: ["workspaces"],
    queryFn: () => WorkspacesService.listWorkspaces(),
  })

  const workspaceId = workspaces?.[0]?.workspace_id

  const {
    data: alerts,
    isLoading: alertsLoading,
    refetch,
  } = useQuery({
    queryKey: ["alerts", workspaceId],
    queryFn: () => AlertsService.listAlerts(workspaceId!),
    enabled: !!workspaceId,
  })

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["alerts", workspaceId] })
  }

  if (wsLoading || alertsLoading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    )
  }

  if (!workspaceId) {
    return (
      <div className="rounded-lg border border-dashed p-8 text-center">
        <Bell className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">
          Create a workspace first to set up alerts.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {alerts?.length ?? 0} alert{alerts?.length !== 1 ? "s" : ""} configured
        </p>

        <Dialog>
          <DialogTrigger asChild>
            <Button size="sm">
              <Plus className="mr-1.5 h-4 w-4" />
              New Alert
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Create Alert</DialogTitle>
            </DialogHeader>
            <CreateAlertDialog
              workspaceId={workspaceId}
              onCreated={invalidate}
            />
          </DialogContent>
        </Dialog>
      </div>

      {alerts?.length === 0 ? (
        <div className="rounded-lg border border-dashed py-12 text-center">
          <Bell className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
          <p className="mb-1 text-sm font-medium">No alerts yet</p>
          <p className="text-xs text-muted-foreground">
            Create an alert to be notified when domain data changes.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {alerts?.map((alert) => (
            <AlertRow
              key={alert.alert_id}
              alert={alert}
              workspaceId={workspaceId}
              onMutated={invalidate}
            />
          ))}
        </div>
      )}
    </div>
  )
}
