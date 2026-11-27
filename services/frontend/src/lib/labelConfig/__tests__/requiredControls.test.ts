import { ParsedComponent, parseLabelConfig } from '../parser'
import {
  extractRequiredControls,
  missingRequiredControls,
} from '../requiredControls'

function parse(xml: string): ParsedComponent {
  const parsed = parseLabelConfig(xml)
  if ('message' in parsed) throw new Error(parsed.message)
  return parsed
}

describe('extractRequiredControls', () => {
  it('lists required controls with their label, else their name', () => {
    const config = parse(`<View>
      <Header value="Section" required="true"/>
      <Rating name="confidence" toName="confidence" required="true" label="How confident?"/>
      <Likert name="ease" toName="ease" required="true"/>
      <TextArea name="comments" toName="comments"/>
    </View>`)
    expect(extractRequiredControls(config)).toEqual([
      { name: 'confidence', type: 'Rating', label: 'How confident?' },
      { name: 'ease', type: 'Likert', label: 'ease' },
    ])
  })

  it('skips required object tags, which mark task data fields', () => {
    const config = parse(`<View>
      <Text name="text" value="$text" required="true"/>
      <Choices name="answer" toName="text" required="true">
        <Choice value="Yes"/>
      </Choices>
    </View>`)
    expect(extractRequiredControls(config).map((c) => c.name)).toEqual([
      'answer',
    ])
  })
})

describe('missingRequiredControls', () => {
  const config = parse(`<View>
    <Rating name="r" toName="r" required="true"/>
    <Choices name="c" toName="c" required="true"><Choice value="A"/></Choices>
    <TextArea name="t" toName="t" required="true"/>
    <Number name="n" toName="n" required="true"/>
  </View>`)
  const names = (results: any[]) =>
    missingRequiredControls(config, results).map((c) => c.name)

  it('reports every required control without a result', () => {
    expect(names([])).toEqual(['r', 'c', 't', 'n'])
  })

  it('counts empty values as unanswered', () => {
    expect(
      names([
        { from_name: 'r', to_name: 'r', type: 'rating', value: { rating: 0 } },
        {
          from_name: 'c',
          to_name: 'c',
          type: 'choices',
          value: { choices: [] },
        },
        {
          from_name: 't',
          to_name: 't',
          type: 'textarea',
          value: { text: [' '] },
        },
        { from_name: 'n', to_name: 'n', type: 'number', value: null },
      ]),
    ).toEqual(['r', 'c', 't', 'n'])
  })

  it('accepts given answers, including a number 0 and raw values', () => {
    expect(
      names([
        { from_name: 'r', to_name: 'text', type: 'textarea', value: 3 },
        { from_name: 'c', to_name: 'text', type: 'textarea', value: 'A' },
        {
          from_name: 't',
          to_name: 't',
          type: 'textarea',
          value: { text: ['x'] },
        },
        { from_name: 'n', to_name: 'n', type: 'number', value: 0 },
      ]),
    ).toEqual([])
  })
})
