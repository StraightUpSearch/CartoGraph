/**
 * /domains — main database table view with filter panel + cursor pagination.
 *
 * Filters are stored in URL search params via TanStack Router's validateSearch
 * so they persist on refresh and can be copied as links.
 */

import { useQuery } from "@tanstack/react-query"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { useState } from "react"
import { z } from "zod"

import { DomainsService } from "@/client/cartograph"
import {
  DomainFilterPanel,
  type DomainFilters,
} from "@/components/Domains/DomainFilterPanel"
import {
  DomainTable,
  DomainTableSkeleton,
} from "@/components/Domains/DomainTable"

// Validate URL search params
const searchSchema = z.object({
  page: z.coerce.number().min(1).optional().default(1),
  page_size: z.coerce.number().min(1).max(500).optional().default(50),
  after_cursor: z.string().optional(),
  platform: z.string().optional(),
  category: z.string().optional(),
  status: z.string().optional(),
  min_dr: z.coerce.number().optional(),
  max_dr: z.coerce.number().optional(),
  min_traffic: z.coerce.number().optional(),
  min_intent: z.coerce.number().optional(),
  shopping_carousel: z
    .enum(["true", "false"])
    .transform((v) => v === "true")
    .optional(),
})

export const Route = createFileRoute("/_layout/domains")({
  validateSearch: searchSchema,
  component: DomainsPage,
  head: () => ({
    meta: [{ title: "Domain Database — CartoGraph" }],
  }),
})

function DomainsPage() {
  const search = Route.useSearch()
  const navigate = useNavigate({ from: "/domains" })

  // Cursor stack for navigating forward through cursor pages
  const [cursorStack, setCursorStack] = useState<string[]>([])

  const filters: DomainFilters = {
    platform: search.platform,
    category: search.category,
    status: search.status as DomainFilters["status"],
    min_dr: search.min_dr,
    max_dr: search.max_dr,
    min_traffic: search.min_traffic,
    min_intent: search.min_intent,
  }

  const { data, isLoading } = useQuery({
    queryKey: [
      "domains",
      search.page,
      search.page_size,
      search.after_cursor,
      search.platform,
      search.category,
      search.status,
      search.min_dr,
      search.max_dr,
      search.min_traffic,
      search.min_intent,
      search.shopping_carousel,
    ],
    queryFn: () =>
      DomainsService.listDomains({
        page: search.page,
        page_size: search.page_size,
        after_cursor: search.after_cursor,
        platform: search.platform,
        category: search.category,
        status: search.status,
        min_dr: search.min_dr,
        max_dr: search.max_dr,
        min_traffic: search.min_traffic,
        min_intent: search.min_intent,
        shopping_carousel: search.shopping_carousel,
      }),
    placeholderData: (prev) => prev,
  })

  const handleFiltersChange = (newFilters: DomainFilters) => {
    setCursorStack([])
    navigate({
      search: {
        ...newFilters,
        page: 1,
        after_cursor: undefined,
        shopping_carousel: undefined,
      },
      replace: true,
    })
  }

  const handlePageChange = (newPage: number) => {
    navigate({
      search: { ...search, page: newPage, after_cursor: undefined },
      replace: true,
    })
  }

  const handleCursorNext = () => {
    if (!data?.next_cursor) return
    setCursorStack((prev) => [...prev, search.after_cursor ?? ""])
    navigate({
      search: {
        ...search,
        after_cursor: data.next_cursor ?? undefined,
        page: 1,
      },
      replace: true,
    })
  }

  return (
    <div className="space-y-6 p-1">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Domain Database</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {data?.count != null
            ? `${data.count.toLocaleString()} domains match your filters`
            : "UK-validated ecommerce domains with commercial intent scoring"}
        </p>
      </div>

      <div className="flex gap-6">
        {/* Filter sidebar */}
        <DomainFilterPanel
          filters={filters}
          onFiltersChange={handleFiltersChange}
        />

        {/* Table */}
        <div className="min-w-0 flex-1">
          {isLoading ? (
            <DomainTableSkeleton />
          ) : (
            <DomainTable
              data={data?.data ?? []}
              total={data?.count ?? 0}
              page={search.page ?? 1}
              pageSize={search.page_size ?? 50}
              nextCursor={data?.next_cursor ?? null}
              loading={isLoading}
              onPageChange={handlePageChange}
              onCursorNext={handleCursorNext}
            />
          )}
        </div>
      </div>
    </div>
  )
}
