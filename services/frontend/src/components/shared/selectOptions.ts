/**
 * Ordering and search for dropdowns whose options come from loaded data
 * (projects, organizations, users, models, groups, ...).
 *
 * Every such dropdown sorts its options alphabetically by the visible label
 * and filters them by what the user types, the same way everywhere. The
 * shared Select applies this in its `searchable` mode; the helpers are
 * exported so the Jest mock of Select and any list outside a Select order
 * options identically.
 */
import React, { Children, Fragment, ReactNode, isValidElement } from 'react'

/**
 * German collation for labels: case-insensitive, umlauts sort with their base
 * letter ("Äpfel" next to "Apfel", not after "Z"), and digits compare as
 * numbers ("Model 2" before "Model 10").
 */
const labelCollator = new Intl.Collator('de', {
  sensitivity: 'base',
  numeric: true,
})
/** Breaks ties between labels the base collation calls equal ("a" / "A"). */
const tieCollator = new Intl.Collator('de', { numeric: true })

export function compareLabels(a: string, b: string): number {
  return labelCollator.compare(a, b) || tieCollator.compare(a, b)
}

/** A copy of `items` sorted alphabetically by `getLabel`. */
export function sortByLabel<T>(
  items: readonly T[],
  getLabel: (item: T) => string,
): T[] {
  return [...items].sort((a, b) => compareLabels(getLabel(a), getLabel(b)))
}

/** Lower case without diacritics, so "a" finds "Ä" and "strasse" finds "Straße". */
export function normalizeForSearch(text: string): string {
  return text
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/ß/g, 'ss')
    .toLowerCase()
    .trim()
}

/** "Ärger" as typed without umlauts: "aerger". */
function transcribeUmlauts(text: string): string {
  return text
    .replace(/[äÄ]/g, 'ae')
    .replace(/[öÖ]/g, 'oe')
    .replace(/[üÜ]/g, 'ue')
}

/**
 * True when every whitespace-separated word of `query` occurs in `label`,
 * ignoring case and diacritics; "ae", "oe" and "ue" also find umlauts.
 */
export function matchesQuery(label: string, query: string): boolean {
  const q = normalizeForSearch(query)
  if (!q) return true
  const haystacks = [
    normalizeForSearch(label),
    normalizeForSearch(transcribeUmlauts(label)),
  ]
  return q
    .split(/\s+/)
    .every((word) => haystacks.some((haystack) => haystack.includes(word)))
}

/** The text a node renders, for sorting and searching by the visible label. */
export function nodeText(node: ReactNode): string {
  if (node === null || node === undefined || typeof node === 'boolean')
    return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(nodeText).join('')
  if (isValidElement(node)) {
    return nodeText((node.props as { children?: ReactNode }).children)
  }
  return ''
}

export interface OptionProps {
  value?: string
  children?: ReactNode
  /** Kept at the top of its group, in source order ("All", "None", ...). */
  pinned?: boolean
  /** Sort and search text when the visible label is not plain text. */
  textValue?: string
}

/** The label an option element sorts and searches by. */
export function optionText(element: React.ReactElement): string {
  const props = element.props as OptionProps
  return props.textValue ?? nodeText(props.children)
}

interface ArrangeOptions {
  /** Marks group headings; options between two headings form one group. */
  isGroupLabel: (element: React.ReactElement) => boolean
  /** Filter text; empty keeps every option. */
  query?: string
}

function flatten(node: ReactNode, out: React.ReactElement[]): void {
  Children.forEach(node, (child) => {
    if (!isValidElement(child)) return
    if (child.type === Fragment) {
      flatten((child.props as { children?: ReactNode }).children, out)
      return
    }
    out.push(child)
  })
}

/**
 * Reorder and filter the children of a dropdown list. Within each group
 * (delimited by group headings) pinned options stay first in source order and
 * the rest sort alphabetically by label. With a query, options that do not
 * match are dropped and headings left without options disappear. Elements
 * that are neither options (no `value` prop) nor headings stay before or
 * after their group's options, wherever they stood in the source.
 */
export function arrangeOptions(
  children: ReactNode,
  { isGroupLabel, query = '' }: ArrangeOptions,
): React.ReactElement[] {
  const elements: React.ReactElement[] = []
  flatten(children, elements)

  interface Group {
    heading: React.ReactElement | null
    pinned: React.ReactElement[]
    sorted: React.ReactElement[]
    /** Non-option elements before the group's first option ... */
    before: React.ReactElement[]
    /** ... and after it (a trailing "Enter manually" action, a note). */
    after: React.ReactElement[]
    seenOption: boolean
  }
  const newGroup = (heading: React.ReactElement | null): Group => ({
    heading,
    pinned: [],
    sorted: [],
    before: [],
    after: [],
    seenOption: false,
  })
  const groups: Group[] = [newGroup(null)]
  for (const element of elements) {
    if (isGroupLabel(element)) {
      groups.push(newGroup(element))
      continue
    }
    const group = groups[groups.length - 1]
    const props = element.props as OptionProps
    if (props.value === undefined) {
      ;(group.seenOption ? group.after : group.before).push(element)
      continue
    }
    group.seenOption = true
    if (!matchesQuery(optionText(element), query)) {
      continue
    } else if (props.pinned) {
      group.pinned.push(element)
    } else {
      group.sorted.push(element)
    }
  }

  const result: React.ReactElement[] = []
  for (const group of groups) {
    const options = [...group.pinned, ...sortByLabel(group.sorted, optionText)]
    // A heading whose options all miss the search goes; the group's other
    // elements stay, so a trailing action remains reachable.
    const hideHeading = options.length === 0 && group.seenOption
    if (group.heading && !hideHeading) result.push(group.heading)
    result.push(...group.before, ...options, ...group.after)
  }
  return result
}

/** Whether any option survives `arrangeOptions` (for an empty-result note). */
export function hasOptions(elements: React.ReactElement[]): boolean {
  return elements.some(
    (element) => (element.props as OptionProps).value !== undefined,
  )
}
