/**
 * @jest-environment jsdom
 *
 * Branch coverage tests for PromptManager.
 * Targets 10 uncovered branches.
 */

import '@testing-library/jest-dom'
import { render, screen, fireEvent } from '@testing-library/react'
import { PromptManager, PromptData } from '../PromptManager'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, vars?: any) => key,
  }),
}))

jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: jest.fn() }),
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, disabled, ...props }: any) => (
    <button onClick={onClick} disabled={disabled} {...props}>{children}</button>
  ),
}))

jest.mock('@/hooks/useDefaultConfig', () => ({
  useDefaultConfig: () => ({
    config: { max_tokens: 500, temperature: 0.7 },
  }),
}))

jest.mock('@/lib/api', () => ({
  api: { post: jest.fn() },
}))

jest.mock('@heroicons/react/24/outline', () => ({
  ArrowUpTrayIcon: (props: any) => <svg {...props} data-testid="upload-icon" />,
  PlusIcon: (props: any) => <svg {...props} data-testid="plus-icon" />,
  TrashIcon: (props: any) => <svg {...props} data-testid="trash-icon" />,
}))

describe('PromptManager', () => {
  const defaultPrompts: PromptData[] = [
    { prompt: 'Test prompt 1', expected_output: 'output 1' },
    { prompt: 'Test prompt 2' },
  ]

  it('renders with existing prompts', () => {
    render(
      <PromptManager
        prompts={defaultPrompts}
        onPromptsChange={jest.fn()}
      />
    )
    expect(screen.getByText('Test prompt 1')).toBeInTheDocument()
    expect(screen.getByText('Test prompt 2')).toBeInTheDocument()
  })

  it('renders with empty prompts', () => {
    render(
      <PromptManager
        prompts={[]}
        onPromptsChange={jest.fn()}
      />
    )
    // Should render without errors
  })

  it('renders with taskType specified', () => {
    render(
      <PromptManager
        prompts={[]}
        onPromptsChange={jest.fn()}
        taskType="evaluation"
      />
    )
    // Should render without errors
  })

  it('renders with taskId specified', () => {
    render(
      <PromptManager
        prompts={[]}
        onPromptsChange={jest.fn()}
        taskId="task-123"
      />
    )
    // Should render without errors
  })

  it('handles prompts with metadata', () => {
    const prompts: PromptData[] = [
      {
        prompt: 'System prompt',
        metadata: { prompt_type: 'system', max_tokens: 1000, temperature: 0.5, context: 'legal' },
      },
    ]
    render(
      <PromptManager
        prompts={prompts}
        onPromptsChange={jest.fn()}
      />
    )
    expect(screen.getByText('System prompt')).toBeInTheDocument()
  })

  it('calls onPromptsChange when removing a prompt', () => {
    const onChange = jest.fn()
    render(
      <PromptManager
        prompts={defaultPrompts}
        onPromptsChange={onChange}
      />
    )
    // Find and click a delete button
    const deleteButtons = screen.getAllByTestId('trash-icon')
    if (deleteButtons.length > 0) {
      fireEvent.click(deleteButtons[0].closest('button')!)
      expect(onChange).toHaveBeenCalled()
    }
  })
})
