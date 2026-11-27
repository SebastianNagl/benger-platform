/**
 * @jest-environment jsdom
 *
 * renderProviderGroupedOptions: the options of a model Select, one group per
 * provider, in the order the API lists the models (catalog order). Jest maps
 * the Select to its native-<select> mock, which drops the headings but orders
 * the options as the real Select does.
 */
import {
  Select,
  SelectContent,
  SelectGroupLabel,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/shared/Select'
import { render, screen } from '@testing-library/react'
import { renderProviderGroupedOptions } from '../ProviderGroupedOptions'

const MODELS = [
  { id: 'gpt-6.2-astra', name: 'GPT-6.2 Astra', provider: 'OpenAI' },
  { id: 'gpt-4.1', name: 'GPT-4.1', provider: 'OpenAI' },
  { id: 'claude-opus-5-5', name: 'Claude Opus 5.5', provider: 'Anthropic' },
  { id: 'claude-haiku-5-5', name: 'Claude Haiku 5.5', provider: 'Anthropic' },
]

function renderPicker(keepOrder: boolean) {
  render(
    <Select
      searchable
      keepOrder={keepOrder}
      value="gpt-4.1"
      onValueChange={jest.fn()}
    >
      <SelectTrigger data-testid="trigger">
        <SelectValue placeholder="Model" />
      </SelectTrigger>
      <SelectContent>
        {renderProviderGroupedOptions(MODELS, (m) => (
          <SelectItem key={m.id} value={m.id}>
            {m.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>,
  )
  const select = screen.getByRole('combobox') as HTMLSelectElement
  return Array.from(select.options, (o) => o.value).filter(Boolean)
}

describe('renderProviderGroupedOptions', () => {
  it('emits a heading per provider followed by its models, in list order', () => {
    const nodes = renderProviderGroupedOptions(MODELS, (m) => (
      <SelectItem key={m.id} value={m.id}>
        {m.name}
      </SelectItem>
    )) as React.ReactElement[]
    const flat = nodes.flatMap((group) => {
      const children = (group.props as { children: React.ReactNode[] }).children
      return children.flat() as React.ReactElement[]
    })
    expect(
      flat.map((el) =>
        el.type === SelectGroupLabel
          ? `# ${(el.props as { children: string }).children}`
          : (el.props as { value: string }).value,
      ),
    ).toEqual([
      '# OpenAI',
      'gpt-6.2-astra',
      'gpt-4.1',
      '# Anthropic',
      'claude-opus-5-5',
      'claude-haiku-5-5',
    ])
  })

  it('keeps the catalog order in a searchable Select with keepOrder', () => {
    expect(renderPicker(true)).toEqual([
      'gpt-6.2-astra',
      'gpt-4.1',
      'claude-opus-5-5',
      'claude-haiku-5-5',
    ])
  })

  it('would be sorted by name within each provider without keepOrder', () => {
    expect(renderPicker(false)).toEqual([
      'gpt-4.1',
      'gpt-6.2-astra',
      'claude-haiku-5-5',
      'claude-opus-5-5',
    ])
  })
})
