'use client'

import { SelectGroupLabel } from '@/components/shared/Select'
import { groupModelsByProvider } from '@/lib/modelOrder'
import { Fragment, type ReactNode } from 'react'

/**
 * The options of a model Select, one group per provider under its name, in
 * the order the API lists the models (see lib/modelOrder). A searchable
 * Select that renders them sets `keepOrder`, or it would sort the models of
 * each group by name.
 *
 * A function, not a component: the Select reads its options from the
 * elements inside SelectContent (expanding Fragments only), so the options
 * must be there as elements, not behind a component.
 */
export function renderProviderGroupedOptions<
  M extends { id: string; provider: string },
>(models: readonly M[], renderOption: (model: M) => ReactNode): ReactNode {
  return groupModelsByProvider(models).map((group) => (
    <Fragment key={group.provider}>
      <SelectGroupLabel>{group.provider}</SelectGroupLabel>
      {group.models.map(renderOption)}
    </Fragment>
  ))
}
