import { Card } from '@/components/shared/Card'

export interface StatTile {
  id: string
  label: string
  value: string
}

/** Headline numbers of the report (tasks, submissions, models, ...). */
export function StatTiles({ tiles }: { tiles: StatTile[] }) {
  if (tiles.length === 0) return null
  return (
    <div
      className="mb-8 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5"
      data-testid="stat-tiles"
    >
      {tiles.map((tile) => (
        <Card key={tile.id} className="p-4" data-testid={`stat-${tile.id}`}>
          <div className="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
            {tile.label}
          </div>
          <div className="mt-1 text-2xl font-semibold tabular-nums text-zinc-900 dark:text-white">
            {tile.value}
          </div>
        </Card>
      ))}
    </div>
  )
}
