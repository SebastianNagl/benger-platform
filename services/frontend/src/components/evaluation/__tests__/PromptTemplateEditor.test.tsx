/**
 * @jest-environment jsdom
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { PromptTemplateEditor } from '../PromptTemplateEditor'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (_key: string, fallback?: string) => fallback || _key,
  }),
}))

function Harness(props: {
  initial?: string
  knownVariables: string[]
  dimensionKeys?: string[]
}) {
  const [value, setValue] = useState(props.initial || '')
  return (
    <PromptTemplateEditor
      value={value}
      onChange={setValue}
      knownVariables={props.knownVariables}
      dimensionKeys={props.dimensionKeys}
    />
  )
}

describe('PromptTemplateEditor', () => {
  it('renders textarea with current value', () => {
    render(
      <Harness
        initial="Hello {{fall}}"
        knownVariables={['fall', 'answer']}
      />
    )
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement
    expect(textarea.value).toBe('Hello {{fall}}')
  })

  it('shows variable pills with ✓ for variables present in the template', () => {
    render(
      <Harness
        initial="Fall: {{fall}}"
        knownVariables={['fall', 'answer']}
      />
    )
    // fall is used → ✓; answer is not → no ✓
    expect(screen.getByRole('button', { name: /\{\{fall\}\}/ }).textContent).toMatch(/✓/)
    expect(screen.getByRole('button', { name: /\{\{answer\}\}/ }).textContent).not.toMatch(/✓/)
  })

  it('warns when template references variables outside knownVariables', () => {
    render(
      <Harness
        initial="Use {{unmapped_var}}"
        knownVariables={['fall']}
      />
    )
    expect(
      screen.getByText(/Template references variables not yet mapped/i)
    ).toBeInTheDocument()
    // The variable appears in both the textarea and the warning <code> tag;
    // assert against the <code> element specifically.
    const codeMatches = screen.getAllByText('unmapped_var').filter(
      (el) => el.tagName.toLowerCase() === 'code'
    )
    expect(codeMatches.length).toBe(1)
  })

  it('warns when dimension keys are not mentioned in the prompt', () => {
    render(
      <Harness
        initial="Empty prompt"
        knownVariables={[]}
        dimensionKeys={['result_correctness', 'clarity']}
      />
    )
    expect(
      screen.getByText(/Dimension keys not mentioned in the prompt/i)
    ).toBeInTheDocument()
    expect(screen.getByText(/result_correctness, clarity/)).toBeInTheDocument()
  })

  it('inserts variable token at cursor when pill clicked', async () => {
    const user = userEvent.setup()
    render(
      <Harness initial="" knownVariables={['fall']} />
    )
    await user.click(screen.getByRole('button', { name: /\{\{fall\}\}/ }))
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement
    expect(textarea.value).toBe('{{fall}}')
  })
})
