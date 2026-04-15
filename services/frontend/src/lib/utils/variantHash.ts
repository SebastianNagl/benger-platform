/**
 * Deterministic variant selection for conditional instructions.
 *
 * Uses a hash of userId + taskId to consistently assign an instruction variant
 * per user per task. Same inputs always produce the same output, so the variant
 * persists across page reloads without any server-side storage.
 */

interface Variant {
  id: string
  weight: number
}

/**
 * djb2 hash function - produces a deterministic 32-bit integer from a string.
 */
function djb2Hash(str: string): number {
  let hash = 5381
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) + hash + str.charCodeAt(i)) & 0xffffffff
  }
  return Math.abs(hash)
}

/**
 * Select a variant deterministically based on userId and taskId.
 *
 * @param userId - The current user's ID
 * @param taskId - The current task's ID
 * @param variants - Array of {id, weight} objects. Weights are relative (e.g., 50/50 or 30/70).
 * @returns The selected variant's ID, or null if variants is empty
 */
export function selectVariant(
  userId: string,
  taskId: string,
  variants: Variant[]
): string | null {
  if (!variants || variants.length === 0) return null
  if (variants.length === 1) return variants[0].id

  const totalWeight = variants.reduce((sum, v) => sum + v.weight, 0)
  if (totalWeight <= 0) return variants[0].id

  const hash = djb2Hash(userId + ':' + taskId)
  const bucket = hash % totalWeight

  let cumulative = 0
  for (const variant of variants) {
    cumulative += variant.weight
    if (bucket < cumulative) {
      return variant.id
    }
  }

  return variants[variants.length - 1].id
}
