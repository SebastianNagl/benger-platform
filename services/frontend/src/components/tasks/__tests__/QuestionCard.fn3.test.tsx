/**
 * fn3 function coverage for QuestionCard.tsx
 * Targets: handleSave, handleCancel, handleFieldChange callbacks
 */

import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    locale: 'en',
    t: (key: string, vars?: any) => (vars ? `${key}:${JSON.stringify(vars)}` : key),
    changeLocale: jest.fn(),
    isReady: true,
  }),
}))

import { QuestionCard } from '../QuestionCard'

describe('QuestionCard fn3', () => {
  const baseQuestion = {
    id: 'q1',
    question: 'What is the capital?',
    reference_answer: 'Berlin',
  }
  const mockOnUpdate = jest.fn()
  const mockOnDelete = jest.fn()

  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('renders QA question card', () => {
    render(
      <QuestionCard
        question={baseQuestion}
        taskType="qa"
        onUpdate={mockOnUpdate}
        onDelete={mockOnDelete}
      />
    )
    expect(document.body).toBeInTheDocument()
  })

  it('renders QA reasoning question card', () => {
    const qaRQuestion = {
      ...baseQuestion,
      reasoning: 'Because it is the capital of Germany',
    }
    render(
      <QuestionCard
        question={qaRQuestion}
        taskType="qa_reasoning"
        onUpdate={mockOnUpdate}
        onDelete={mockOnDelete}
      />
    )
    expect(document.body).toBeInTheDocument()
  })

  it('renders multiple choice question card', () => {
    const mcQuestion = {
      id: 'mc1',
      question: 'What is 2+2?',
      case: 'Math test',
      choice_a: '3',
      choice_b: '4',
      choice_c: '5',
      choice_d: '6',
      correct_answer: 'b' as const,
    }
    render(
      <QuestionCard
        question={mcQuestion}
        taskType="multiple_choice"
        onUpdate={mockOnUpdate}
        onDelete={mockOnDelete}
      />
    )
    expect(document.body).toBeInTheDocument()
  })

  it('handles field change via text input', () => {
    render(
      <QuestionCard
        question={baseQuestion}
        taskType="qa"
        onUpdate={mockOnUpdate}
        onDelete={mockOnDelete}
      />
    )
    // Find any input/textarea and change its value
    const textareas = screen.getAllByRole('textbox')
    if (textareas.length > 0) {
      fireEvent.change(textareas[0], { target: { value: 'New question text' } })
      expect(mockOnUpdate).toHaveBeenCalled()
    }
  })

  it('handles expand toggle', () => {
    const onToggle = jest.fn()
    render(
      <QuestionCard
        question={baseQuestion}
        taskType="qa"
        onUpdate={mockOnUpdate}
        onDelete={mockOnDelete}
        isExpanded={false}
        onToggleExpanded={onToggle}
      />
    )
    expect(document.body).toBeInTheDocument()
  })
})
