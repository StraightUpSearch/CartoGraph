/**
 * DomainFilterPanel — sidebar filter controls for the domains table.
 *
 * All filter values are driven by URL search params (via TanStack Router's
 * validateSearch) so they persist on refresh and can be shared via link.
 */

import { zodResolver } from "@hookform/resolvers/zod"
import { Filter, RotateCcw } from "lucide-react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { Button } from "@/components/ui/button"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"

export const domainFilterSchema = z.object({
  platform: z.string().optional(),
  category: z.string().optional(),
  min_dr: z.coerce.number().min(0).max(100).optional(),
  max_dr: z.coerce.number().min(0).max(100).optional(),
  min_traffic: z.coerce.number().min(0).optional(),
  min_intent: z.coerce.number().min(1).max(10).optional(),
  status: z.enum(["active", "inactive", "pending", ""]).optional(),
  shopping_carousel: z
    .enum(["true", "false", ""])
    .transform((v) => (v === "true" ? true : v === "false" ? false : undefined))
    .optional(),
})

export type DomainFilters = z.infer<typeof domainFilterSchema>

const PLATFORM_OPTIONS = [
  "Shopify",
  "WooCommerce",
  "Magento",
  "BigCommerce",
  "PrestaShop",
  "Wix",
  "Squarespace",
  "Custom",
]

interface DomainFilterPanelProps {
  filters: DomainFilters
  onFiltersChange: (filters: DomainFilters) => void
}

export function DomainFilterPanel({
  filters,
  onFiltersChange,
}: DomainFilterPanelProps) {
  const form = useForm<DomainFilters>({
    resolver: zodResolver(domainFilterSchema),
    defaultValues: filters,
  })

  const handleSubmit = (values: DomainFilters) => {
    onFiltersChange(values)
  }

  const handleReset = () => {
    form.reset({})
    onFiltersChange({})
  }

  return (
    <aside className="w-64 shrink-0 rounded-lg border bg-card p-4">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2 font-semibold text-sm">
          <Filter className="h-4 w-4" />
          Filters
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={handleReset}
          className="h-7 px-2 text-xs"
        >
          <RotateCcw className="mr-1 h-3 w-3" />
          Reset
        </Button>
      </div>

      <Form {...form}>
        <form
          onSubmit={form.handleSubmit(handleSubmit)}
          className="space-y-4"
        >
          {/* Platform */}
          <FormField
            control={form.control}
            name="platform"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-xs">Platform</FormLabel>
                <Select
                  onValueChange={field.onChange}
                  value={field.value ?? ""}
                >
                  <FormControl>
                    <SelectTrigger className="h-8 text-xs">
                      <SelectValue placeholder="Any platform" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem value="">Any</SelectItem>
                    {PLATFORM_OPTIONS.map((p) => (
                      <SelectItem key={p} value={p}>
                        {p}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </FormItem>
            )}
          />

          {/* Status */}
          <FormField
            control={form.control}
            name="status"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-xs">Status</FormLabel>
                <Select
                  onValueChange={field.onChange}
                  value={field.value ?? ""}
                >
                  <FormControl>
                    <SelectTrigger className="h-8 text-xs">
                      <SelectValue placeholder="Any status" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem value="">Any</SelectItem>
                    <SelectItem value="active">Active</SelectItem>
                    <SelectItem value="inactive">Inactive</SelectItem>
                    <SelectItem value="pending">Pending</SelectItem>
                  </SelectContent>
                </Select>
              </FormItem>
            )}
          />

          <Separator />

          {/* DR range */}
          <div>
            <p className="mb-2 text-xs font-medium">Domain Rating</p>
            <div className="flex items-center gap-2">
              <FormField
                control={form.control}
                name="min_dr"
                render={({ field }) => (
                  <FormItem className="flex-1">
                    <FormControl>
                      <Input
                        {...field}
                        type="number"
                        placeholder="Min"
                        min={0}
                        max={100}
                        className="h-8 text-xs"
                        value={field.value ?? ""}
                      />
                    </FormControl>
                  </FormItem>
                )}
              />
              <span className="text-xs text-muted-foreground">–</span>
              <FormField
                control={form.control}
                name="max_dr"
                render={({ field }) => (
                  <FormItem className="flex-1">
                    <FormControl>
                      <Input
                        {...field}
                        type="number"
                        placeholder="Max"
                        min={0}
                        max={100}
                        className="h-8 text-xs"
                        value={field.value ?? ""}
                      />
                    </FormControl>
                  </FormItem>
                )}
              />
            </div>
          </div>

          {/* Min traffic */}
          <FormField
            control={form.control}
            name="min_traffic"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-xs">Min Monthly Traffic</FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    type="number"
                    placeholder="e.g. 1000"
                    min={0}
                    className="h-8 text-xs"
                    value={field.value ?? ""}
                  />
                </FormControl>
              </FormItem>
            )}
          />

          {/* Min intent score */}
          <FormField
            control={form.control}
            name="min_intent"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-xs">
                  Min Intent Score (1–10)
                </FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    type="number"
                    placeholder="e.g. 6"
                    min={1}
                    max={10}
                    className="h-8 text-xs"
                    value={field.value ?? ""}
                  />
                </FormControl>
              </FormItem>
            )}
          />

          {/* Category */}
          <FormField
            control={form.control}
            name="category"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-xs">Category</FormLabel>
                <FormControl>
                  <Input
                    {...field}
                    placeholder="e.g. Fashion"
                    className="h-8 text-xs"
                    value={field.value ?? ""}
                  />
                </FormControl>
              </FormItem>
            )}
          />

          {/* Shopping carousel */}
          <FormField
            control={form.control}
            name="shopping_carousel"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-xs">Shopping Carousel</FormLabel>
                <Select
                  onValueChange={field.onChange}
                  value={
                    field.value === true
                      ? "true"
                      : field.value === false
                        ? "false"
                        : ""
                  }
                >
                  <FormControl>
                    <SelectTrigger className="h-8 text-xs">
                      <SelectValue placeholder="Any" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem value="">Any</SelectItem>
                    <SelectItem value="true">Yes</SelectItem>
                    <SelectItem value="false">No</SelectItem>
                  </SelectContent>
                </Select>
              </FormItem>
            )}
          />

          <Button type="submit" className="w-full" size="sm">
            Apply Filters
          </Button>
        </form>
      </Form>
    </aside>
  )
}
