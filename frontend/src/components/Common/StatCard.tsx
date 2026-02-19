import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import type { LucideIcon } from "lucide-react"

interface StatCardProps {
  title: string
  value: number | string | undefined
  icon: LucideIcon
  description?: string
  loading?: boolean
  suffix?: string
}

export function StatCard({
  title,
  value,
  icon: Icon,
  description,
  loading = false,
  suffix,
}: StatCardProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {title}
        </CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-8 w-24" />
        ) : (
          <div className="text-3xl font-bold">
            {typeof value === "number" ? value.toLocaleString() : value}
            {suffix && (
              <span className="ml-1 text-sm font-normal text-muted-foreground">
                {suffix}
              </span>
            )}
          </div>
        )}
        {description && (
          <p className="mt-1 text-xs text-muted-foreground">{description}</p>
        )}
      </CardContent>
    </Card>
  )
}
