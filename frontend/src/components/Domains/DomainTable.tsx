/**
 * DomainTable — sortable, paginated table for the domains database view.
 *
 * Uses @tanstack/react-table for column definitions + React Query for data.
 * Cursor-pagination is available via the next_cursor field from the API.
 */

import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table"
import { ArrowRight, ExternalLink, Loader2 } from "lucide-react"
import { Link } from "@tanstack/react-router"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import type { DomainSummary } from "@/client/cartograph"

const STATUS_COLORS: Record<string, string> = {
  active: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  inactive:
    "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200",
  pending:
    "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
}

function IntentBar({ score }: { score: number | null }) {
  if (score === null) return <span className="text-xs text-muted-foreground">—</span>
  const pct = (score / 10) * 100
  const color =
    score >= 7
      ? "bg-green-500"
      : score >= 4
        ? "bg-yellow-500"
        : "bg-red-400"
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-muted">
        <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs tabular-nums">{score}/10</span>
    </div>
  )
}

const columns: ColumnDef<DomainSummary>[] = [
  {
    accessorKey: "domain",
    header: "Domain",
    cell: ({ row }) => (
      <div className="flex items-center gap-2">
        <Link
          to="/domains/$domainId"
          params={{ domainId: row.original.domain_id }}
          className="font-medium text-foreground hover:underline"
        >
          {row.original.domain}
        </Link>
        <a
          href={`https://${row.original.domain}`}
          target="_blank"
          rel="noopener noreferrer"
          className="text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity"
          title="Open site"
        >
          <ExternalLink className="h-3 w-3" />
        </a>
      </div>
    ),
  },
  {
    accessorKey: "platform",
    header: "Platform",
    cell: ({ row }) =>
      row.original.platform ? (
        <Badge variant="outline" className="text-xs">
          {row.original.platform}
        </Badge>
      ) : (
        <span className="text-xs text-muted-foreground">—</span>
      ),
  },
  {
    accessorKey: "category_primary",
    header: "Category",
    cell: ({ row }) =>
      row.original.category_primary ?? (
        <span className="text-xs text-muted-foreground">—</span>
      ),
  },
  {
    accessorKey: "domain_rating",
    header: "DR",
    cell: ({ row }) => (
      <span className="tabular-nums font-medium">
        {row.original.domain_rating ?? "—"}
      </span>
    ),
  },
  {
    accessorKey: "organic_traffic_estimate",
    header: "Traffic/mo",
    cell: ({ row }) => {
      const v = row.original.organic_traffic_estimate
      return v != null ? (
        <span className="tabular-nums text-sm">{v.toLocaleString()}</span>
      ) : (
        <span className="text-xs text-muted-foreground">—</span>
      )
    },
  },
  {
    accessorKey: "commercial_intent_score",
    header: "Intent",
    cell: ({ row }) => (
      <IntentBar score={row.original.commercial_intent_score} />
    ),
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => (
      <span
        className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[row.original.status] ?? ""}`}
      >
        {row.original.status}
      </span>
    ),
  },
  {
    accessorKey: "last_updated_at",
    header: "Updated",
    cell: ({ row }) => {
      const d = new Date(row.original.last_updated_at)
      return (
        <span className="text-xs text-muted-foreground">
          {d.toLocaleDateString("en-GB", {
            day: "numeric",
            month: "short",
            year: "numeric",
          })}
        </span>
      )
    },
  },
  {
    id: "actions",
    cell: ({ row }) => (
      <Link
        to="/domains/$domainId"
        params={{ domainId: row.original.domain_id }}
      >
        <Button variant="ghost" size="sm" className="h-7 px-2">
          <ArrowRight className="h-3.5 w-3.5" />
        </Button>
      </Link>
    ),
  },
]

interface DomainTableProps {
  data: DomainSummary[]
  total: number
  page: number
  pageSize: number
  nextCursor: string | null
  loading?: boolean
  onPageChange: (page: number) => void
  onCursorNext: () => void
}

export function DomainTable({
  data,
  total,
  page,
  pageSize,
  nextCursor,
  loading = false,
  onPageChange,
  onCursorNext,
}: DomainTableProps) {
  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    manualPagination: true,
    rowCount: total,
  })

  const totalPages = Math.ceil(total / pageSize)

  if (loading) {
    return (
      <div className="space-y-2">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((hg) => (
              <TableRow key={hg.id}>
                {hg.headers.map((h) => (
                  <TableHead key={h.id} className="text-xs font-semibold">
                    {h.isPlaceholder
                      ? null
                      : flexRender(h.column.columnDef.header, h.getContext())}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={columns.length}
                  className="py-12 text-center text-sm text-muted-foreground"
                >
                  No domains found. Try adjusting the filters.
                </TableCell>
              </TableRow>
            ) : (
              table.getRowModel().rows.map((row) => (
                <TableRow
                  key={row.id}
                  className="group cursor-pointer hover:bg-muted/50"
                >
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id} className="py-2.5 text-sm">
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext(),
                      )}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Pagination controls */}
      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>
          {total.toLocaleString()} domain{total !== 1 ? "s" : ""} total
        </span>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => onPageChange(page - 1)}
          >
            Previous
          </Button>
          <span className="tabular-nums">
            Page {page} of {Math.max(totalPages, 1)}
          </span>
          {nextCursor ? (
            <Button variant="outline" size="sm" onClick={onCursorNext}>
              Next
            </Button>
          ) : (
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => onPageChange(page + 1)}
            >
              Next
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

export function DomainTableSkeleton() {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        <span className="text-sm text-muted-foreground">Loading domains…</span>
      </div>
      {Array.from({ length: 10 }).map((_, i) => (
        <Skeleton key={i} className="h-11 w-full" />
      ))}
    </div>
  )
}
