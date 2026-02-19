/**
 * CartoGraph API — hand-written client types and services.
 *
 * Until the OpenAPI spec is regenerated from the live backend these types
 * mirror the Pydantic models in backend/app/models.py and the route
 * handlers in backend/app/api/routes/*.py.
 *
 * Usage:
 *   import { DomainsService, type DomainSummary } from "@/client/cartograph"
 */

import type { CancelablePromise } from "./core/CancelablePromise"
import { OpenAPI } from "./core/OpenAPI"
import { request as __request } from "./core/request"

// ---------------------------------------------------------------------------
// Domain types
// ---------------------------------------------------------------------------

export interface DomainSummary {
  domain_id: string
  domain: string
  country: string
  tld: string | null
  status: string
  first_seen_at: string
  last_updated_at: string
  schema_version: string
  domain_rating: number | null
  organic_traffic_estimate: number | null
  commercial_intent_score: number | null
  platform: string | null
  category_primary: string | null
  confidence_value: number | null
}

export interface DomainsPublic {
  data: DomainSummary[]
  count: number
  page: number
  next_cursor: string | null
}

export interface DomainPublic {
  domain_id: string
  domain: string
  country: string
  tld: string | null
  status: string
  first_seen_at: string
  last_updated_at: string
  schema_version: string
  discovery: Record<string, unknown> | null
  ecommerce: Record<string, unknown> | null
  seo_metrics: Record<string, unknown> | null
  intent_layer: Record<string, unknown> | null
  serp_intelligence: Record<string, unknown> | null
  technical_layer: Record<string, unknown> | null
  contact: Record<string, unknown> | null
  marketplace_overlap: Record<string, unknown> | null
  paid_ads_presence: Record<string, unknown> | null
  meta: Record<string, unknown> | null
  change_tracking: Record<string, unknown> | null
  confidence_score: Record<string, unknown> | null
  pipeline: Record<string, unknown> | null
  ai_summary: Record<string, unknown> | null
  // Per-group gating flags from mask_domain_by_tier
  [key: string]: unknown
}

export interface DomainStats {
  total_domains: number
  active_domains: number
  new_this_week: number
}

export interface DomainListParams {
  page?: number
  page_size?: number
  after_cursor?: string
  country?: string
  status?: string
  platform?: string
  category?: string
  min_dr?: number
  max_dr?: number
  min_traffic?: number
  min_intent?: number
  shopping_carousel?: boolean
}

// ---------------------------------------------------------------------------
// Workspace types
// ---------------------------------------------------------------------------

export interface WorkspacePublic {
  workspace_id: string
  name: string
  tier: string
  api_token_prefix: string | null
  domain_lookups_used: number
  export_credits_used: number
  api_calls_used: number
  billing_cycle_start: string
  created_at: string
}

export interface WorkspaceCreate {
  name: string
}

export interface WorkspaceUsage {
  tier: string
  billing_cycle_start: string
  domain_lookups: { used: number; limit: number | null }
  export_credits: { used: number; limit: number | null }
  api_calls: { used: number; limit: number | null }
}

// ---------------------------------------------------------------------------
// Alert types
// ---------------------------------------------------------------------------

export type AlertType = "new_domain" | "tech_change" | "dr_change" | "serp_feature"

export interface AlertPublic {
  alert_id: string
  workspace_id: string
  name: string
  alert_type: AlertType
  filter_criteria: Record<string, unknown> | null
  threshold: Record<string, unknown> | null
  is_active: boolean
  last_triggered: string | null
  created_at: string
}

export interface AlertCreate {
  name: string
  alert_type: AlertType
  filter_criteria?: Record<string, unknown>
  threshold?: Record<string, unknown>
  delivery?: Record<string, unknown>
}

// ---------------------------------------------------------------------------
// Webhook types
// ---------------------------------------------------------------------------

export type WebhookEventType = "domain.created" | "domain.updated" | "alert.triggered"

export interface WebhookPublic {
  webhook_id: string
  workspace_id: string
  url: string
  event_types: WebhookEventType[]
  is_active: boolean
  created_at: string
}

export interface WebhookCreate {
  url: string
  event_types: WebhookEventType[]
}

// ---------------------------------------------------------------------------
// Domains service
// ---------------------------------------------------------------------------

export class DomainsService {
  public static getDomainStats(): CancelablePromise<DomainStats> {
    return __request(OpenAPI, {
      method: "GET",
      url: "/api/v1/domains/stats",
      errors: { 422: "Validation Error" },
    })
  }

  public static listDomains(
    params: DomainListParams = {},
  ): CancelablePromise<DomainsPublic> {
    return __request(OpenAPI, {
      method: "GET",
      url: "/api/v1/domains/",
      query: {
        page: params.page,
        page_size: params.page_size,
        after_cursor: params.after_cursor,
        country: params.country,
        status: params.status,
        platform: params.platform,
        category: params.category,
        min_dr: params.min_dr,
        max_dr: params.max_dr,
        min_traffic: params.min_traffic,
        min_intent: params.min_intent,
        shopping_carousel: params.shopping_carousel,
      },
      errors: { 422: "Validation Error" },
    })
  }

  public static getDomain(domainId: string): CancelablePromise<DomainPublic> {
    return __request(OpenAPI, {
      method: "GET",
      url: "/api/v1/domains/{domain_id}",
      path: { domain_id: domainId },
      errors: { 404: "Not Found", 422: "Validation Error" },
    })
  }

  public static getDomainByName(
    domainName: string,
  ): CancelablePromise<DomainPublic> {
    return __request(OpenAPI, {
      method: "GET",
      url: "/api/v1/domains/by-name/{domain_name}",
      path: { domain_name: domainName },
      errors: { 404: "Not Found", 422: "Validation Error" },
    })
  }

  public static importDomains(
    domains: Array<{ domain: string; tags?: string[] }>,
  ): CancelablePromise<{
    status: string
    created: number
    queued_for_enrichment: number
    skipped_existing: number
  }> {
    return __request(OpenAPI, {
      method: "POST",
      url: "/api/v1/domains/import",
      body: domains,
      mediaType: "application/json",
      errors: { 422: "Validation Error" },
    })
  }
}

// ---------------------------------------------------------------------------
// Workspaces service
// ---------------------------------------------------------------------------

export class WorkspacesService {
  public static listWorkspaces(): CancelablePromise<WorkspacePublic[]> {
    return __request(OpenAPI, {
      method: "GET",
      url: "/api/v1/workspaces/",
      errors: { 422: "Validation Error" },
    })
  }

  public static createWorkspace(
    data: WorkspaceCreate,
  ): CancelablePromise<WorkspacePublic> {
    return __request(OpenAPI, {
      method: "POST",
      url: "/api/v1/workspaces/",
      body: data,
      mediaType: "application/json",
      errors: { 422: "Validation Error" },
    })
  }

  public static getWorkspace(
    workspaceId: string,
  ): CancelablePromise<WorkspacePublic> {
    return __request(OpenAPI, {
      method: "GET",
      url: "/api/v1/workspaces/{workspace_id}",
      path: { workspace_id: workspaceId },
      errors: { 404: "Not Found", 422: "Validation Error" },
    })
  }

  public static getWorkspaceUsage(
    workspaceId: string,
  ): CancelablePromise<WorkspaceUsage> {
    return __request(OpenAPI, {
      method: "GET",
      url: "/api/v1/workspaces/{workspace_id}/usage",
      path: { workspace_id: workspaceId },
      errors: { 404: "Not Found", 422: "Validation Error" },
    })
  }

  public static rotateToken(
    workspaceId: string,
  ): CancelablePromise<{ token: string; prefix: string; warning: string }> {
    return __request(OpenAPI, {
      method: "POST",
      url: "/api/v1/workspaces/{workspace_id}/token",
      path: { workspace_id: workspaceId },
      errors: { 404: "Not Found", 422: "Validation Error" },
    })
  }
}

// ---------------------------------------------------------------------------
// Alerts service
// ---------------------------------------------------------------------------

export class AlertsService {
  public static listAlerts(
    workspaceId: string,
  ): CancelablePromise<AlertPublic[]> {
    return __request(OpenAPI, {
      method: "GET",
      url: "/api/v1/workspaces/{workspace_id}/alerts",
      path: { workspace_id: workspaceId },
      errors: { 422: "Validation Error" },
    })
  }

  public static createAlert(
    workspaceId: string,
    data: AlertCreate,
  ): CancelablePromise<AlertPublic> {
    return __request(OpenAPI, {
      method: "POST",
      url: "/api/v1/workspaces/{workspace_id}/alerts",
      path: { workspace_id: workspaceId },
      body: data,
      mediaType: "application/json",
      errors: { 422: "Validation Error" },
    })
  }

  public static updateAlert(
    workspaceId: string,
    alertId: string,
    data: AlertCreate,
  ): CancelablePromise<AlertPublic> {
    return __request(OpenAPI, {
      method: "PATCH",
      url: "/api/v1/workspaces/{workspace_id}/alerts/{alert_id}",
      path: { workspace_id: workspaceId, alert_id: alertId },
      body: data,
      mediaType: "application/json",
      errors: { 422: "Validation Error" },
    })
  }

  public static toggleAlert(
    workspaceId: string,
    alertId: string,
  ): CancelablePromise<AlertPublic> {
    return __request(OpenAPI, {
      method: "PATCH",
      url: "/api/v1/workspaces/{workspace_id}/alerts/{alert_id}/toggle",
      path: { workspace_id: workspaceId, alert_id: alertId },
      errors: { 422: "Validation Error" },
    })
  }

  public static deleteAlert(
    workspaceId: string,
    alertId: string,
  ): CancelablePromise<void> {
    return __request(OpenAPI, {
      method: "DELETE",
      url: "/api/v1/workspaces/{workspace_id}/alerts/{alert_id}",
      path: { workspace_id: workspaceId, alert_id: alertId },
      errors: { 422: "Validation Error" },
    })
  }
}

// ---------------------------------------------------------------------------
// Webhooks service
// ---------------------------------------------------------------------------

export class WebhooksService {
  public static listWebhooks(
    workspaceId: string,
  ): CancelablePromise<WebhookPublic[]> {
    return __request(OpenAPI, {
      method: "GET",
      url: "/api/v1/workspaces/{workspace_id}/webhooks",
      path: { workspace_id: workspaceId },
      errors: { 422: "Validation Error" },
    })
  }

  public static createWebhook(
    workspaceId: string,
    data: WebhookCreate,
  ): CancelablePromise<WebhookPublic> {
    return __request(OpenAPI, {
      method: "POST",
      url: "/api/v1/workspaces/{workspace_id}/webhooks",
      path: { workspace_id: workspaceId },
      body: data,
      mediaType: "application/json",
      errors: { 422: "Validation Error" },
    })
  }

  public static deleteWebhook(
    workspaceId: string,
    webhookId: string,
  ): CancelablePromise<void> {
    return __request(OpenAPI, {
      method: "DELETE",
      url: "/api/v1/workspaces/{workspace_id}/webhooks/{webhook_id}",
      path: { workspace_id: workspaceId, webhook_id: webhookId },
      errors: { 422: "Validation Error" },
    })
  }

  public static testWebhook(
    workspaceId: string,
    webhookId: string,
  ): CancelablePromise<{ status: string; webhook_id: string }> {
    return __request(OpenAPI, {
      method: "POST",
      url: "/api/v1/workspaces/{workspace_id}/webhooks/{webhook_id}/test",
      path: { workspace_id: workspaceId, webhook_id: webhookId },
      errors: { 422: "Validation Error" },
    })
  }
}
