/**
 * @jest-environment jsdom
 */

import { resolveDataBinding, validateTaskDataFields } from '../dataBinding'
import { extractFieldsFromLabelConfig } from '../fieldExtractor'
import {
  extractImportDataFields,
  extractRequiredDataFields,
  parseLabelConfig,
  type ParsedComponent,
} from '../parser'
import {
  expandRepeaters,
  hasRepeater,
  repeaterItems,
  resolveDataPath,
} from '../repeater'

const DOCKET = `<View>
  <Header value="Docket"/>
  <Repeater on="$cases" indexFlag="{{idx}}" mode="pagination" answerKey="case" style="gap: 4px">
    <Text name="case_{{idx}}" value="$cases[{{idx}}].text" required="true"/>
    <Number name="risk_{{idx}}" toName="case_{{idx}}" min="0" max="100"/>
    <Header value="Item {{idx}}">Item {{idx}}</Header>
  </Repeater>
  <TextArea name="summary" toName="intro"/>
</View>`

const TASK = {
  cases: [{ text: 'First case.' }, { text: 'Second case.' }],
}

function parse(xml: string, taskData?: Record<string, any>): ParsedComponent {
  const parsed = parseLabelConfig(xml, taskData)
  if ('message' in parsed) throw new Error(parsed.message)
  return parsed
}

function names(node: ParsedComponent): string[] {
  return [
    ...(node.name ? [node.name] : []),
    ...node.children.flatMap((child) => names(child)),
  ]
}

describe('expandRepeaters', () => {
  it('repeats the children per item with the 0-based index, as Label Studio does', () => {
    const tree = parse(DOCKET, TASK)
    expect(hasRepeater(tree)).toBe(false)
    expect(names(tree)).toEqual([
      'case_0',
      'risk_0',
      'case_1',
      'risk_1',
      'summary',
    ])
    const block = tree.children[1]
    expect(block.type).toBe('View')
    expect(block.props).toEqual({ style: 'gap: 4px' })
    expect(block.children.map((c) => c.type)).toEqual(['View', 'View'])
    const [text, number, header] = block.children[1].children
    expect(text.props.value).toBe('$cases[1].text')
    expect(number.props.toName).toBe('case_1')
    expect(number.name).toBe('risk_1')
    // attributes are substituted, text content is not
    expect(header.props.value).toBe('Item 1')
    expect(header.props.content).toBe('Item {{idx}}')
  })

  it('keeps the Repeater without task data and returns trees without one as they are', () => {
    const raw = parse(DOCKET)
    expect(hasRepeater(raw)).toBe(true)
    const plain = parse('<View><TextArea name="a" toName="t"/></View>')
    expect(expandRepeaters(plain, TASK)).toBe(plain)
  })

  it('repeats nothing when the binding names no array', () => {
    for (const data of [{}, { cases: 'text' }, { cases: null }]) {
      expect(names(parse(DOCKET, data))).toEqual(['summary'])
    }
  })

  it('honours a custom index flag, attribute case and nested data paths', () => {
    const tree = parse(
      `<View><Repeater ON="$doc.items" indexflag="#n"><TextArea name="t_#n" toName="x_#n"/></Repeater></View>`,
      { doc: { items: [1, 2, 3] } },
    )
    expect(names(tree)).toEqual(['t_0', 't_1', 't_2'])
  })

  it('looks the array up exactly, as Label Studio and the backend do', () => {
    const repeater = parse(DOCKET).children[1]
    expect(repeaterItems(repeater, TASK)).toHaveLength(2)
    // keys are case-sensitive and the task is not searched for a data wrapper
    expect(repeaterItems(repeater, { Cases: TASK.cases })).toEqual([])
    expect(names(parse(DOCKET, { Cases: TASK.cases }))).toEqual(['summary'])
    expect(repeaterItems(repeater, { data: TASK })).toEqual([])
    expect(repeaterItems({ ...repeater, props: {} }, TASK)).toEqual([])
  })

  it('resolves data paths like lodash get', () => {
    const data = { a: { b: [{ c: 5 }] } }
    expect(resolveDataPath('$a.b[0].c', data)).toBe(5)
    expect(resolveDataPath('$a.b.0.c', data)).toBe(5)
    expect(resolveDataPath('$a.b[3].c', data)).toBeUndefined()
    expect(resolveDataPath('$A.b', data)).toBeUndefined()
    expect(resolveDataPath('a.b', data)).toBeUndefined()
    expect(resolveDataPath('$a.b.x', data)).toBeUndefined()
  })
})

describe('data bindings into expanded items', () => {
  it('resolves bracket and dot indexes', () => {
    expect(resolveDataBinding('$cases[1].text', TASK)).toBe('Second case.')
    expect(resolveDataBinding('$cases.0.text', TASK)).toBe('First case.')
    expect(resolveDataBinding('$cases[5].text', TASK)).toBeUndefined()
  })

  it('checks required bindings of the expanded tree against the task', () => {
    const required = extractRequiredDataFields(parse(DOCKET, TASK))
    expect(required).toEqual(['cases[0].text', 'cases[1].text'])
    expect(validateTaskDataFields(required, TASK).valid).toBe(true)
    expect(
      validateTaskDataFields(required, { cases: [{ text: 'only one' }] })
        .missingFields,
    ).toEqual(['cases[1].text'])
  })
})

describe('import fields of a Repeater config', () => {
  it('expects the repeated array, not the per-item bindings', () => {
    expect(extractImportDataFields(parse(DOCKET))).toEqual({
      required: ['cases'],
      optional: [],
    })
  })

  it('reads the on attribute in any case, as the expansion does', () => {
    const tree = parse(
      '<View><Repeater ON="$items"><TextArea name="t_{{idx}}" toName="x"/></Repeater></View>',
    )
    expect(extractImportDataFields(tree)).toEqual({
      required: ['items'],
      optional: [],
    })
  })
})

describe('wizard fields of a Repeater config', () => {
  const CONFIG = `<View>
  <Text name="intro" value="$intro"/>
  <Repeater on="$cases">
    <Text name="case_{{idx}}" value="$cases[{{idx}}].text"/>
    <Number name="risk_{{idx}}" toName="case_{{idx}}"/>
  </Repeater>
  <TextArea name="summary" toName="intro"/>
</View>`

  it('lists indexed names to the longest array of the imported tasks', () => {
    const fields = extractFieldsFromLabelConfig(CONFIG, [
      { cases: [{ text: 'a' }] },
      { cases: [{ text: 'a' }, { text: 'b' }, { text: 'c' }] },
      { intro: 'no cases' },
    ])
    expect(fields.outputFields.map((f) => f.name)).toEqual([
      'risk_0',
      'risk_1',
      'risk_2',
      'summary',
    ])
    expect(fields.outputFields[1].toName).toBe('case_1')
    expect(fields.inputFields.sort()).toEqual(['cases', 'intro'])
  })

  it('lists no Repeater fields and no template names without task data', () => {
    const fields = extractFieldsFromLabelConfig(CONFIG)
    expect(fields.outputFields.map((f) => f.name)).toEqual(['summary'])
    expect(fields.inputFields.sort()).toEqual(['cases', 'intro'])
  })
})
