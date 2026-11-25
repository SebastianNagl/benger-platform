/**
 * @jest-environment jsdom
 *
 * Typing a long answer into a TextArea field without a pause, the way the
 * browser delivers it: one native input event per key, each handled and
 * committed on its own (outside act(), which would batch them).
 *
 * The form hands every typed value straight back to the field. The field
 * used to take it again in an effect, which scheduled one more update per
 * key; after about fifty keys React stopped with "Maximum update depth
 * exceeded" and the key typed at that moment was lost (seen on the
 * annotation review page: "fällig" saved as "fälig").
 */
import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'
import { DynamicAnnotationInterface } from '../DynamicAnnotationInterface'

jest.mock('@/contexts/I18nContext', () => {
  const t = (key: string) => key
  return { useI18n: () => ({ t, locale: 'de' }) }
})

const CONFIG =
  "<View><Text name='text' value='$text'/><TextArea name='loesung' toName='text'/></View>"
const ANSWER =
  'Der Anspruch aus § 433 II BGB ist entstanden und fällig, weil der Kaufvertrag wirksam geschlossen wurde.'

/** Types `text` key by key into the textarea, as native input events. */
function typeKeys(box: HTMLTextAreaElement, text: string) {
  const setValue = Object.getOwnPropertyDescriptor(
    HTMLTextAreaElement.prototype,
    'value',
  )!.set!
  let typed = box.value
  for (const key of text) {
    typed += key
    setValue.call(box, typed)
    box.dispatchEvent(new Event('input', { bubbles: true }))
  }
}

describe('DynamicAnnotationInterface: typing into a TextArea', () => {
  let errors: string[]
  let actEnvironment: unknown

  beforeEach(() => {
    errors = []
    jest.spyOn(console, 'error').mockImplementation((...args: unknown[]) => {
      errors.push(String(args[0]))
    })
    actEnvironment = (globalThis as any).IS_REACT_ACT_ENVIRONMENT
  })

  afterEach(() => {
    ;(globalThis as any).IS_REACT_ACT_ENVIRONMENT = actEnvironment
    jest.restoreAllMocks()
  })

  it.each([
    ['an empty field', undefined],
    [
      "the annotator's answer under review",
      [
        {
          from_name: 'loesung',
          to_name: 'text',
          type: 'textarea',
          value: { text: ['Erste Fassung. '] },
        },
      ],
    ],
  ])(
    'keeps every key of a long answer typed without a pause (%s)',
    async (_case, initialValues) => {
      render(
        <DynamicAnnotationInterface
          labelConfig={CONFIG}
          taskData={{ text: 'Sachverhalt' }}
          initialValues={initialValues as any}
          onSubmit={() => {}}
          onChange={() => {}}
          taskId="task-1"
          showSubmitButton={false}
          enableAutoSave={false}
        />,
      )
      const box = (await screen.findByRole('textbox')) as HTMLTextAreaElement
      const before = box.value

      ;(globalThis as any).IS_REACT_ACT_ENVIRONMENT = false
      typeKeys(box, ANSWER)
      await new Promise((resolve) => setTimeout(resolve, 0))

      expect(errors.filter((e) => e.includes('Maximum update depth'))).toEqual(
        [],
      )
      expect(box.value).toBe(before + ANSWER)
    },
  )
})
