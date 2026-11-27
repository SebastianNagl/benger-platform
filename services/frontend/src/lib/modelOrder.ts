/**
 * The order models are picked in.
 *
 * The model lists of the API (available-models, the public catalog) come in
 * catalog order: one block per provider, the newest and most capable model
 * first within a provider (services/shared/seeds/llm_models.yaml, stored as
 * llm_models.display_order), custom models after the catalog. Pickers keep
 * that order rather than sorting by name, and show each provider block
 * under its name.
 */

export interface ProviderGroup<M> {
  provider: string
  models: M[]
}

/**
 * The models grouped by provider, keeping the order they came in: groups in
 * the order their providers first appear, models in list order within a
 * group.
 */
export function groupModelsByProvider<M extends { provider: string }>(
  models: readonly M[],
): ProviderGroup<M>[] {
  const groups = new Map<string, M[]>()
  for (const model of models) {
    const group = groups.get(model.provider)
    if (group) group.push(model)
    else groups.set(model.provider, [model])
  }
  return Array.from(groups, ([provider, grouped]) => ({
    provider,
    models: grouped,
  }))
}
