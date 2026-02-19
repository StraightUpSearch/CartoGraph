/**
 * DomainProfileTabs — full domain profile with per-tab JSONB sections.
 *
 * Tabs:
 *   Overview    — identity, confidence, discovery method, meta
 *   SEO         — DR, DA, traffic, backlinks, spam score
 *   Technology  — detected tech stack, platform, checkout signals
 *   SERP        — SERP features, top queries, paid ads
 *   Contact     — social profiles, email signals (gated)
 *   History     — month-on-month changes, trending score
 */

import { ExternalLink, Lock, TrendingDown, TrendingUp } from "lucide-react"
import { useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { GatedField, UpgradeModal } from "@/components/Common/UpgradeModal"
import { TierBadge } from "@/components/Common/TierBadge"
import type { DomainPublic } from "@/client/cartograph"

// ---------------------------------------------------------------------------
// Field rendering helpers
// ---------------------------------------------------------------------------

function FieldRow({
  label,
  value,
}: {
  label: string
  value: React.ReactNode
}) {
  return (
    <div className="flex items-start justify-between gap-4 py-2.5 text-sm border-b last:border-0">
      <span className="shrink-0 text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value ?? "—"}</span>
    </div>
  )
}

function JsonBlob({ data }: { data: Record<string, unknown> | null }) {
  if (!data) return <span className="text-xs text-muted-foreground">No data</span>
  return (
    <pre className="overflow-auto rounded bg-muted p-3 text-xs leading-relaxed">
      {JSON.stringify(data, null, 2)}
    </pre>
  )
}

function GatedSection({ label, tier }: { label: string; tier: string }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-dashed p-4">
      <Lock className="h-4 w-4 text-muted-foreground" />
      <span className="text-sm text-muted-foreground">
        {label} is gated on your current{" "}
        <TierBadge tier={tier} /> plan.
      </span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab panels
// ---------------------------------------------------------------------------

function OverviewTab({ domain }: { domain: DomainPublic }) {
  const meta = domain.meta as Record<string, unknown> | null
  const conf = domain.confidence_score as Record<string, unknown> | null
  const disc = domain.discovery as Record<string, unknown> | null

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Domain Identity</CardTitle>
        </CardHeader>
        <CardContent>
          <FieldRow label="Domain" value={
            <a
              href={`https://${domain.domain}`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-primary hover:underline"
            >
              {domain.domain}
              <ExternalLink className="h-3 w-3" />
            </a>
          } />
          <FieldRow label="Country" value={domain.country} />
          <FieldRow label="TLD" value={domain.tld} />
          <FieldRow label="Status" value={
            <Badge
              variant={domain.status === "active" ? "default" : "secondary"}
              className="text-xs"
            >
              {domain.status}
            </Badge>
          } />
          <FieldRow label="First Seen" value={
            new Date(domain.first_seen_at).toLocaleDateString("en-GB", {
              day: "numeric", month: "long", year: "numeric",
            })
          } />
          <FieldRow label="Last Updated" value={
            new Date(domain.last_updated_at).toLocaleDateString("en-GB", {
              day: "numeric", month: "long", year: "numeric",
            })
          } />
        </CardContent>
      </Card>

      {conf && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Confidence Score</CardTitle>
          </CardHeader>
          <CardContent>
            <FieldRow
              label="Score"
              value={`${((conf.value as number) * 100).toFixed(0)}%`}
            />
            {Array.isArray(conf.evidence) && conf.evidence.length > 0 && (
              <div className="mt-2 space-y-1">
                {(conf.evidence as string[]).map((e, i) => (
                  <div key={i} className="flex items-center gap-2 text-xs">
                    <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
                    {e}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {disc && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Discovery</CardTitle>
          </CardHeader>
          <CardContent>
            <FieldRow label="Method" value={String(disc.method ?? "—")} />
            <FieldRow label="Intent Type" value={String(disc.intent_type ?? "—")} />
          </CardContent>
        </Card>
      )}

      {meta && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Technical Meta</CardTitle>
          </CardHeader>
          <CardContent>
            <FieldRow label="SSL Valid" value={meta.ssl_valid ? "Yes" : "No"} />
            <FieldRow label="Mobile Friendly" value={meta.mobile_friendly ? "Yes" : "No"} />
            {meta.page_speed_score != null && (
              <FieldRow label="Page Speed" value={`${meta.page_speed_score}/100`} />
            )}
            <FieldRow label="Language" value={String(meta.language ?? "—")} />
          </CardContent>
        </Card>
      )}

      {domain.ai_summary && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">AI Summary</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm leading-relaxed">
              {String((domain.ai_summary as Record<string, unknown>).summary ?? "No summary available.")}
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function SeoTab({ domain }: { domain: DomainPublic }) {
  if ((domain as Record<string, unknown>).seo_metrics_gated) {
    return <GatedSection label="SEO Metrics" tier="starter" />
  }
  const seo = domain.seo_metrics as Record<string, unknown> | null
  if (!seo) return <p className="text-sm text-muted-foreground">No SEO data yet. Enrichment pending.</p>

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">SEO Metrics</CardTitle>
      </CardHeader>
      <CardContent>
        <FieldRow label="Domain Rating (Ahrefs)" value={String(seo.domain_rating ?? "—")} />
        <FieldRow label="Domain Authority (Moz)" value={
          (domain as Record<string, unknown>).seo_metrics_da_gated
            ? <GatedField tier="Professional" feature="Domain Authority" />
            : String(seo.domain_authority ?? "—")
        } />
        <FieldRow label="Organic Traffic / mo" value={
          seo.organic_traffic_estimate
            ? Number(seo.organic_traffic_estimate).toLocaleString()
            : "—"
        } />
        <FieldRow label="Referring Domains" value={
          seo.referring_domains_count
            ? Number(seo.referring_domains_count).toLocaleString()
            : "—"
        } />
        <FieldRow label="Spam Score" value={seo.spam_score != null ? `${seo.spam_score}/100` : "—"} />
        {seo.authority_divergence_flag && (
          <div className="mt-2 rounded-md bg-yellow-50 p-3 text-xs text-yellow-800 dark:bg-yellow-950 dark:text-yellow-200">
            ⚠ DR and DA diverge by more than 30 points — verify data quality
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function TechTab({ domain }: { domain: DomainPublic }) {
  if ((domain as Record<string, unknown>).technical_layer_gated) {
    return <GatedSection label="Technology Stack" tier="starter" />
  }
  const tech = domain.technical_layer as Record<string, unknown> | null
  const ecom = domain.ecommerce as Record<string, unknown> | null

  return (
    <div className="space-y-4">
      {ecom && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Ecommerce Platform</CardTitle>
          </CardHeader>
          <CardContent>
            <FieldRow label="Platform" value={String(ecom.platform ?? "—")} />
            <FieldRow label="Plan" value={String(ecom.platform_plan ?? "—")} />
            <FieldRow label="Category" value={String(ecom.category_primary ?? "—")} />
            <FieldRow
              label="Product Count Est."
              value={ecom.product_count_estimate != null
                ? Number(ecom.product_count_estimate).toLocaleString()
                : "—"
              }
            />
            <FieldRow
              label="Checkout Detected"
              value={ecom.has_checkout ? "Yes" : "No"}
            />
          </CardContent>
        </Card>
      )}

      {tech && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Full Tech Stack</CardTitle>
          </CardHeader>
          <CardContent>
            {Array.isArray(tech.tech_stack) && tech.tech_stack.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {(tech.tech_stack as string[]).map((t) => (
                  <Badge key={t} variant="outline" className="text-xs">
                    {t}
                  </Badge>
                ))}
              </div>
            ) : (
              <span className="text-sm text-muted-foreground">No tech detected</span>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function SerpTab({ domain }: { domain: DomainPublic }) {
  if ((domain as Record<string, unknown>).serp_intelligence_gated) {
    return <GatedSection label="SERP Intelligence" tier="starter" />
  }
  const serp = domain.serp_intelligence as Record<string, unknown> | null
  const paid = domain.paid_ads_presence as Record<string, unknown> | null
  const intent = domain.intent_layer as Record<string, unknown> | null

  return (
    <div className="space-y-4">
      {serp && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">SERP Features</CardTitle>
          </CardHeader>
          <CardContent>
            {typeof serp.serp_features === "object" && serp.serp_features ? (
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(serp.serp_features as Record<string, boolean>)
                  .filter(([, active]) => active)
                  .map(([feat]) => (
                    <Badge key={feat} variant="secondary" className="text-xs">
                      {feat.replace(/_/g, " ")}
                    </Badge>
                  ))}
              </div>
            ) : null}
          </CardContent>
        </Card>
      )}

      {intent && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Commercial Intent</CardTitle>
          </CardHeader>
          <CardContent>
            <FieldRow label="Intent Score" value={`${intent.commercial_intent_score}/10`} />
            <FieldRow label="Modifier Density" value={
              intent.modifier_density != null
                ? `${(Number(intent.modifier_density) * 100).toFixed(1)}%`
                : "—"
            } />
          </CardContent>
        </Card>
      )}

      {paid && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Paid Ads Presence</CardTitle>
          </CardHeader>
          <CardContent>
            <FieldRow label="Google Shopping" value={paid.google_shopping ? "Yes" : "No"} />
            <FieldRow label="Google Ads" value={paid.google_ads ? "Yes" : "No"} />
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function ContactTab({ domain }: { domain: DomainPublic }) {
  if ((domain as Record<string, unknown>).contact_gated) {
    return <GatedSection label="Contact & Social Data" tier="professional" />
  }
  const contact = domain.contact as Record<string, unknown> | null
  if (!contact) return <p className="text-sm text-muted-foreground">No contact data available.</p>

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Contact Signals</CardTitle>
      </CardHeader>
      <CardContent>
        <FieldRow label="Contact Form" value={contact.has_contact_form ? "Yes" : "No"} />
        {typeof contact.social_profiles === "object" && contact.social_profiles && (
          <div className="mt-2 space-y-1">
            <p className="text-xs font-medium text-muted-foreground">Social</p>
            {Object.entries(contact.social_profiles as Record<string, string>).map(
              ([network, url]) => (
                <div key={network} className="flex items-center gap-2 text-sm">
                  <span className="capitalize text-muted-foreground">{network}:</span>
                  <a href={url} target="_blank" rel="noopener noreferrer"
                    className="text-primary hover:underline text-xs">
                    {url}
                  </a>
                </div>
              ),
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function HistoryTab({ domain }: { domain: DomainPublic }) {
  if ((domain as Record<string, unknown>).change_tracking_gated) {
    return <GatedSection label="Change History" tier="professional" />
  }
  const changes = domain.change_tracking as Record<string, unknown> | null
  if (!changes) return <p className="text-sm text-muted-foreground">No change history yet.</p>

  const trafficDelta = changes.mom_traffic_delta as number | null
  const trending = changes.trending_score as number | null

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Month-on-Month Changes</CardTitle>
        </CardHeader>
        <CardContent>
          <FieldRow
            label="Traffic Delta"
            value={
              trafficDelta != null ? (
                <span className={`flex items-center gap-1 ${trafficDelta >= 0 ? "text-green-600" : "text-red-600"}`}>
                  {trafficDelta >= 0 ? (
                    <TrendingUp className="h-3.5 w-3.5" />
                  ) : (
                    <TrendingDown className="h-3.5 w-3.5" />
                  )}
                  {trafficDelta >= 0 ? "+" : ""}{trafficDelta.toFixed(1)}%
                </span>
              ) : "—"
            }
          />
          <FieldRow
            label="Trending Score"
            value={trending != null ? `${trending.toFixed(1)} / 10` : "—"}
          />
          {Array.isArray(changes.feature_gains) && changes.feature_gains.length > 0 && (
            <div className="mt-2">
              <p className="mb-1 text-xs font-medium text-muted-foreground">SERP feature gains</p>
              <div className="flex flex-wrap gap-1">
                {(changes.feature_gains as string[]).map((f) => (
                  <Badge key={f} className="bg-green-100 text-green-800 text-xs hover:bg-green-100">
                    +{f.replace(/_/g, " ")}
                  </Badge>
                ))}
              </div>
            </div>
          )}
          {Array.isArray(changes.feature_losses) && changes.feature_losses.length > 0 && (
            <div className="mt-2">
              <p className="mb-1 text-xs font-medium text-muted-foreground">SERP feature losses</p>
              <div className="flex flex-wrap gap-1">
                {(changes.feature_losses as string[]).map((f) => (
                  <Badge key={f} variant="destructive" className="text-xs">
                    -{f.replace(/_/g, " ")}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface DomainProfileTabsProps {
  domain: DomainPublic
  tier?: string
}

export function DomainProfileTabs({
  domain,
  tier = "free",
}: DomainProfileTabsProps) {
  const [upgradeOpen, setUpgradeOpen] = useState(false)
  const [requiredTier, setRequiredTier] = useState("starter")

  return (
    <>
      <Tabs defaultValue="overview" className="w-full">
        <TabsList className="mb-4 flex-wrap">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="seo">SEO Metrics</TabsTrigger>
          <TabsTrigger value="tech">Technology</TabsTrigger>
          <TabsTrigger value="serp">SERP</TabsTrigger>
          <TabsTrigger value="contact">Contact</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <OverviewTab domain={domain} />
        </TabsContent>
        <TabsContent value="seo">
          <SeoTab domain={domain} />
        </TabsContent>
        <TabsContent value="tech">
          <TechTab domain={domain} />
        </TabsContent>
        <TabsContent value="serp">
          <SerpTab domain={domain} />
        </TabsContent>
        <TabsContent value="contact">
          <ContactTab domain={domain} />
        </TabsContent>
        <TabsContent value="history">
          <HistoryTab domain={domain} />
        </TabsContent>
      </Tabs>

      <UpgradeModal
        open={upgradeOpen}
        onOpenChange={setUpgradeOpen}
        currentTier={tier}
        requiredTier={requiredTier}
        featureName="this data"
      />
    </>
  )
}
