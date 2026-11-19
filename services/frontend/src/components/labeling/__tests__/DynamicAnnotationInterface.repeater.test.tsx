/**
 * @jest-environment jsdom
 */

/**
 * A <Repeater> label config renders one set of controls per item of the
 * task's array, under the indexed names Label Studio uses (risk_0, risk_1),
 * and the submitted results carry those names. The real parser and data
 * binding run; only the leaf components are stand-ins.
 */

import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { DynamicAnnotationInterface } from '../DynamicAnnotationInterface'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (key: string) => key, locale: 'en' }),
}))

jest.mock('@/components/shared/Alert', () => ({
  Alert: function MockAlert({ children }: any) {
    return <div data-testid="alert">{children}</div>
  },
}))

jest.mock('@/components/shared/Skeleton', () => ({
  Skeleton: function MockSkeleton() {
    return <div data-testid="skeleton" />
  },
}))

jest.mock('@/lib/labelConfig/registry', () => {
  const View = ({ children }: any) => <div data-testid="view">{children}</div>
  const Text = ({ config }: any) => (
    <p data-testid={`text-${config.name}`}>{config.props.value}</p>
  )
  const NumberInput = ({ config, value, onChange }: any) => (
    <input
      aria-label={config.name}
      data-to-name={config.props.toName}
      value={value ?? ''}
      onChange={(e) => onChange(Number(e.target.value))}
    />
  )
  const components: Record<string, any> = {
    View: { component: View, category: 'visual' },
    Text: { component: Text, category: 'object' },
    Number: { component: NumberInput, category: 'control' },
  }
  return {
    getComponent: (type: string) => components[type],
    createComponentInstance: jest.fn(),
  }
})

const DOCKET = `<View>
  <Repeater on="$cases" indexFlag="{{idx}}" mode="pagination" answerKey="case">
    <Text name="case_{{idx}}" value="$cases[{{idx}}].text"/>
    <Number name="risk_{{idx}}" toName="case_{{idx}}" min="0" max="100"/>
  </Repeater>
</View>`

describe('DynamicAnnotationInterface with a Repeater', () => {
  it('renders each item with its own indexed controls and submits them', async () => {
    const onSubmit = jest.fn().mockResolvedValue(undefined)
    render(
      <DynamicAnnotationInterface
        labelConfig={DOCKET}
        taskData={{
          cases: [{ text: 'First case.' }, { text: 'Second case.' }],
        }}
        onSubmit={onSubmit}
        enableAutoSave={false}
      />,
    )

    expect(await screen.findByTestId('text-case_0')).toHaveTextContent(
      'First case.',
    )
    expect(screen.getByTestId('text-case_1')).toHaveTextContent('Second case.')
    const second = screen.getByLabelText('risk_1')
    expect(second).toHaveAttribute('data-to-name', 'case_1')
    expect(screen.queryByLabelText('risk_{{idx}}')).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('risk_0'), {
      target: { value: '45' },
    })
    fireEvent.change(second, { target: { value: '60' } })
    fireEvent.click(
      screen.getByRole('button', { name: /annotation.interface.submit/ }),
    )

    await waitFor(() => expect(onSubmit).toHaveBeenCalled())
    const submitted = onSubmit.mock.calls[0][0]
    expect(
      Object.fromEntries(submitted.map((r: any) => [r.from_name, r.value])),
    ).toEqual({ risk_0: 45, risk_1: 60 })
  })

  it('shows no item controls for a task without the array', async () => {
    render(
      <DynamicAnnotationInterface
        labelConfig={DOCKET}
        taskData={{ other: 'x' }}
        onSubmit={jest.fn()}
        enableAutoSave={false}
      />,
    )
    await waitFor(() =>
      expect(screen.queryByTestId('alert')).not.toBeInTheDocument(),
    )
    expect(screen.queryByLabelText(/risk_/)).not.toBeInTheDocument()
  })
})
