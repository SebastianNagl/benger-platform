/**
 * Ordering and search shared by every data dropdown (searchable Select).
 */
import React from 'react'
import {
  arrangeOptions,
  compareLabels,
  hasOptions,
  matchesQuery,
  nodeText,
  normalizeForSearch,
  sortByLabel,
} from '../selectOptions'

const Item = (_props: {
  value: string
  children?: React.ReactNode
  pinned?: boolean
  textValue?: string
}) => null
const Heading = (_props: { children: React.ReactNode }) => null
const isGroupLabel = (element: React.ReactElement) => element.type === Heading

/** Values (or heading/other markers) in the order arrangeOptions returns. */
const order = (elements: React.ReactElement[]) =>
  elements.map((element) => {
    const props = element.props as {
      value?: string
      children?: React.ReactNode
    }
    if (element.type === Heading) return `# ${nodeText(props.children)}`
    return props.value ?? `<${nodeText(props.children)}>`
  })

describe('compareLabels / sortByLabel', () => {
  const sort = (labels: string[]) => sortByLabel(labels, (label) => label)

  it('sorts case-insensitively', () => {
    expect(sort(['beta', 'Alpha', 'gamma', 'Delta'])).toEqual([
      'Alpha',
      'beta',
      'Delta',
      'gamma',
    ])
  })

  it('sorts umlauts with their base letter, as German readers expect', () => {
    expect(
      sort(['Zürich', 'Ärztekammer', 'Bonn', 'Aachen', 'Öko', 'Ost']),
    ).toEqual(['Aachen', 'Ärztekammer', 'Bonn', 'Öko', 'Ost', 'Zürich'])
  })

  it('sorts ß like ss', () => {
    expect(sort(['Strauß', 'Strasse', 'Strand'])).toEqual([
      'Strand',
      'Strasse',
      'Strauß',
    ])
  })

  it('compares digits as numbers', () => {
    expect(sort(['Model 10', 'Model 2', 'Model 1'])).toEqual([
      'Model 1',
      'Model 2',
      'Model 10',
    ])
  })

  it('orders labels equal apart from case deterministically', () => {
    expect(compareLabels('a', 'A')).not.toBe(0)
    expect(sort(['A', 'a'])).toEqual(sort(['a', 'A']))
  })

  it('does not mutate its input', () => {
    const input = ['b', 'a']
    sort(input)
    expect(input).toEqual(['b', 'a'])
  })
})

describe('normalizeForSearch / matchesQuery', () => {
  it('drops case and diacritics', () => {
    expect(normalizeForSearch('  Ärztekammer Zürich ')).toBe(
      'arztekammer zurich',
    )
    expect(normalizeForSearch('Straße')).toBe('strasse')
  })

  it('finds umlaut labels from plain letters and the other way round', () => {
    expect(matchesQuery('Ärztekammer', 'arzt')).toBe(true)
    expect(matchesQuery('Arztpraxis', 'ärzt')).toBe(true)
    expect(matchesQuery('Straße', 'strasse')).toBe(true)
  })

  it('finds umlauts typed as ae, oe and ue', () => {
    expect(matchesQuery('Ärztekammer', 'aerzte')).toBe(true)
    expect(matchesQuery('Öffentliches Recht', 'oeffentlich')).toBe(true)
    expect(matchesQuery('Zürich', 'zuerich')).toBe(true)
    expect(matchesQuery('Zurich', 'zuerich')).toBe(false)
  })

  it('needs every word of the query, in any order', () => {
    expect(matchesQuery('GPT-4o (OpenAI)', 'openai gpt')).toBe(true)
    expect(matchesQuery('GPT-4o (OpenAI)', 'openai claude')).toBe(false)
  })

  it('matches everything for an empty or blank query', () => {
    expect(matchesQuery('anything', '')).toBe(true)
    expect(matchesQuery('anything', '   ')).toBe(true)
  })
})

describe('nodeText', () => {
  it('reads the text of nested elements, arrays and numbers', () => {
    expect(
      nodeText(
        <span>
          {'Model '}
          <b>{2}</b>
          {[' (', 'OpenAI', ')']}
          {false}
          {null}
        </span>,
      ),
    ).toBe('Model 2 (OpenAI)')
  })
})

describe('arrangeOptions', () => {
  it('sorts options by label and keeps pinned ones first in source order', () => {
    const arranged = arrangeOptions(
      [
        <Item key="all" value="all" pinned>
          All projects
        </Item>,
        <Item key="z" value="z">
          Zeta
        </Item>,
        <Item key="none" value="none" pinned>
          None
        </Item>,
        <Item key="a" value="a">
          alpha
        </Item>,
        <Item key="ae" value="ae">
          Ärger
        </Item>,
      ],
      { isGroupLabel },
    )
    expect(order(arranged)).toEqual(['all', 'none', 'a', 'ae', 'z'])
  })

  it('sorts each group on its own and keeps the groups in place', () => {
    const arranged = arrangeOptions(
      <>
        <Heading>Official</Heading>
        <Item value="o2">Sonnet</Item>
        <Item value="o1">Haiku</Item>
        <Heading>Custom</Heading>
        <Item value="c2">Zephyr</Item>
        <Item value="c1">Mistral</Item>
      </>,
      { isGroupLabel },
    )
    expect(order(arranged)).toEqual([
      '# Official',
      'o1',
      'o2',
      '# Custom',
      'c1',
      'c2',
    ])
  })

  it('looks through fragments and arrays', () => {
    const arranged = arrangeOptions(
      [
        [
          <Item key="b" value="b">
            B
          </Item>,
        ],
        <React.Fragment key="f">
          <Item value="a">A</Item>
        </React.Fragment>,
      ],
      { isGroupLabel },
    )
    expect(order(arranged)).toEqual(['a', 'b'])
  })

  it('sorts and searches by textValue when given', () => {
    const arranged = arrangeOptions(
      [
        <Item key="1" value="1" textValue="Beta">
          <span>zzz</span>
        </Item>,
        <Item key="2" value="2" textValue="Alpha">
          <span>yyy</span>
        </Item>,
      ],
      { isGroupLabel },
    )
    expect(order(arranged)).toEqual(['2', '1'])
    expect(
      order(arrangeOptions(arranged, { isGroupLabel, query: 'beta' })),
    ).toEqual(['1'])
  })

  it('filters by query, pinned options included, and hides empty headings', () => {
    const children = (
      <>
        <Item value="all" pinned>
          All
        </Item>
        <Heading>Official</Heading>
        <Item value="o1">Haiku</Item>
        <Heading>Custom</Heading>
        <Item value="c1">Ärztemodell</Item>
      </>
    )
    expect(
      order(arrangeOptions(children, { isGroupLabel, query: 'arzt' })),
    ).toEqual(['# Custom', 'c1'])
    expect(
      order(arrangeOptions(children, { isGroupLabel, query: 'all' })),
    ).toEqual(['all'])
  })

  it('keeps non-option elements before or after the options they stood by', () => {
    const arranged = arrangeOptions(
      <>
        <div>note</div>
        <Item value="b">B</Item>
        <Item value="a">A</Item>
        <div>action</div>
      </>,
      { isGroupLabel, query: 'nothing matches' },
    )
    expect(order(arranged)).toEqual(['<note>', '<action>'])
    expect(hasOptions(arranged)).toBe(false)
    expect(
      hasOptions(arrangeOptions(<Item value="a">A</Item>, { isGroupLabel })),
    ).toBe(true)
  })
})
