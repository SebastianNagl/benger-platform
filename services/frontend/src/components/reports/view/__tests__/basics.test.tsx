import React from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { REPORT_SNAPSHOT_FIXTURE as FIX } from '@/lib/reports/fixture'
import { t } from '../__mocks__/testUtils'
import { ConfigSelector, configOptionLabel } from '../ConfigSelector'
import { MethodsList } from '../MethodsList'
import { ModelChips } from '../ModelChips'
import { ParticipantsList } from '../ParticipantsList'
import { ReportHeader } from '../ReportHeader'
import { StatTiles } from '../StatTiles'
import { StatusCard } from '../StatusCard'
import { ChartLegend, ChartTooltipBox } from '../ChartTooltip'
import { Prose, QuietNote, ReportSection, SubHeading } from '../ReportSection'

jest.mock('next/link', () => ({
  __esModule: true,
  default: ({ href, children, ...rest }: any) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}))

describe('ReportHeader', () => {
  it('renders title, description, dates and draft badge', () => {
    render(
      <ReportHeader
        title="Benchathon 2026"
        description="Beschreibung"
        publishedAt="2026-09-01T10:00:00Z"
        generatedAt="2026-09-02T12:00:00Z"
        isDraft
        editHref="/projects/p1/report/edit"
        locale="de"
        t={t}
      />,
    )
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('Benchathon 2026')
    expect(screen.getByText('Beschreibung')).toBeInTheDocument()
    expect(screen.getByTestId('draft-badge')).toHaveTextContent('Entwurf')
    expect(screen.getByText(/Veröffentlicht am/)).toBeInTheDocument()
    expect(screen.getByTestId('data-as-of')).toHaveTextContent(/Datenstand: .*2026/)
    expect(screen.getByRole('link', { name: 'Bearbeiten' })).toHaveAttribute('href', '/projects/p1/report/edit')
  })

  it('omits optional parts', () => {
    render(<ReportHeader title="X" isDraft={false} locale="de" t={t} />)
    expect(screen.queryByTestId('draft-badge')).not.toBeInTheDocument()
    expect(screen.queryByText(/Veröffentlicht am/)).not.toBeInTheDocument()
    expect(screen.queryByTestId('data-as-of')).not.toBeInTheDocument()
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
  })
})

describe('StatTiles', () => {
  it('renders one card per tile and nothing when empty', () => {
    const { rerender } = render(
      <StatTiles
        tiles={[
          { id: 'tasks', label: 'Aufgaben', value: '15' },
          { id: 'models', label: 'Modelle', value: '4' },
        ]}
      />,
    )
    expect(screen.getByTestId('stat-tasks')).toHaveTextContent('Aufgaben15')
    expect(screen.getByTestId('stat-models')).toHaveTextContent('4')
    rerender(<StatTiles tiles={[]} />)
    expect(screen.queryByTestId('stat-tiles')).not.toBeInTheDocument()
  })
})

describe('ModelChips', () => {
  it('renders chips with id/provider tooltip and groups custom models', () => {
    render(
      <ModelChips
        models={[
          ...FIX.models,
          { id: 'byom-1', kind: 'model', label: 'Mein Modell', provider: 'custom', is_custom: true },
        ]}
        t={t}
      />,
    )
    const chips = screen.getAllByTestId('model-chip')
    expect(chips).toHaveLength(5)
    expect(chips[0]).toHaveAttribute('title', 'gpt-5.4 · openai')
    expect(screen.getByText('Eigene Modelle')).toBeInTheDocument()
    expect(screen.getByText('Mein Modell')).toBeInTheDocument()
  })

  it('renders nothing without models and no custom group without custom ones', () => {
    const { container, rerender } = render(<ModelChips models={[]} t={t} />)
    expect(container).toBeEmptyDOMElement()
    rerender(<ModelChips models={[{ id: 'm', kind: 'model', label: 'M' }]} t={t} />)
    expect(screen.queryByText('Eigene Modelle')).not.toBeInTheDocument()
    expect(screen.getByTestId('model-chip')).toHaveAttribute('title', 'm')
  })
})

describe('ParticipantsList', () => {
  it('lists pseudonyms with counts inside a collapsible', () => {
    render(<ParticipantsList participants={FIX.participants} locale="de" t={t} />)
    expect(screen.getByTestId('participants-list')).toBeInTheDocument()
    expect(screen.getByText('KindAlly')).toBeInTheDocument()
    expect(screen.getByText('8 Abgaben')).toBeInTheDocument()
    expect(screen.getByText(/\(3\)/)).toBeInTheDocument()
  })

  it('renders nothing for an empty list', () => {
    const { container } = render(<ParticipantsList participants={[]} locale="de" t={t} />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('MethodsList', () => {
  it('shows methods with scale/category and config chips', () => {
    render(
      <MethodsList
        methods={FIX.methods.filter((m) => !m.derived)}
        configs={FIX.configs}
        labelFor={(id) => `L:${id}`}
        locale="de"
        t={t}
      />,
    )
    expect(screen.getByText('L:llm_judge_falloesung')).toBeInTheDocument()
    expect(screen.getByText(/0–100 Punkte · LLM-Bewertung/)).toBeInTheDocument()
    expect(screen.getByText(/Menschliche Korrektur/)).toBeInTheDocument()
    expect(screen.getByText(/Lexikalische Metrik/)).toBeInTheDocument()
    const chips = screen.getAllByTestId('config-chip')
    expect(chips).toHaveLength(4)
    expect(chips[0]).toHaveTextContent('Judge: Claude Sonnet 4.6 · n = 900')
    expect(chips[2]).toHaveTextContent('Korrektur · n = 184')
    expect(chips[3]).toHaveTextContent('L:bleu · n = 300')
  })

  it('maps remaining categories and renders nothing when empty', () => {
    const { container, rerender } = render(<MethodsList methods={[]} configs={[]} labelFor={(x) => x} locale="de" t={t} />)
    expect(container).toBeEmptyDOMElement()
    rerender(
      <MethodsList
        methods={[
          { id: 'a', name: 'A', category: 'semantic', scale: '0-1', higher_is_better: true },
          { id: 'b', name: 'B', category: 'classification', scale: 'raw', higher_is_better: true },
          { id: 'c', name: 'C', category: 'other', scale: 'raw', higher_is_better: true },
        ]}
        configs={[]}
        labelFor={(x) => x}
        locale="de"
        t={t}
      />,
    )
    expect(screen.getByText(/Semantische Metrik/)).toBeInTheDocument()
    expect(screen.getByText(/Klassifikation/)).toBeInTheDocument()
    expect(screen.getByText(/Rohwert · other/)).toBeInTheDocument()
  })
})

describe('ConfigSelector', () => {
  const options = FIX.configs.filter((c) => c.metric === 'llm_judge_falloesung')

  it('renders a radiogroup and reports changes', () => {
    const onChange = jest.fn()
    render(<ConfigSelector options={options} value="cfg-judge-sonnet" onChange={onChange} t={t} />)
    const radios = screen.getAllByRole('radio')
    expect(radios).toHaveLength(2)
    expect(radios[0]).toHaveAttribute('aria-checked', 'true')
    expect(radios[1]).toHaveTextContent('GPT-5 mini')
    fireEvent.click(radios[1])
    expect(onChange).toHaveBeenCalledWith('cfg-judge-mini')
  })

  it('hides itself with fewer than two options', () => {
    const { container } = render(<ConfigSelector options={[options[0]]} value={null} onChange={jest.fn()} t={t} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('falls back from judge label to name to id to metric', () => {
    expect(configOptionLabel({ id: 'x', metric: 'm', judge_model: null, judge_label: null, name: 'Name', n: 1 })).toBe('Name')
    expect(configOptionLabel({ id: 'x', metric: 'm', judge_model: null, judge_label: null, name: null, n: 1 })).toBe('x')
    // Two configs on the same judge model: the bare judge name would repeat,
    // so each falls back to its configuration name.
    const a = { id: 'a', metric: 'm', judge_model: 'gpt-5-mini', judge_label: 'GPT-5 Mini', name: 'Judge (×3)', n: 3 }
    const b = { id: 'b', metric: 'm', judge_model: 'gpt-5-mini', judge_label: 'GPT-5 Mini', name: 'Judge (single)', n: 1 }
    const c = { id: 'c', metric: 'm', judge_model: 'gpt-5.4-mini', judge_label: 'GPT-5.4 Mini', name: 'Other', n: 1 }
    expect(configOptionLabel(a, [a, b, c])).toBe('Judge (×3)')
    expect(configOptionLabel(b, [a, b, c])).toBe('Judge (single)')
    expect(configOptionLabel(c, [a, b, c])).toBe('GPT-5.4 Mini')
    expect(configOptionLabel({ id: '', metric: 'm', judge_model: null, judge_label: null, name: null, n: 1 })).toBe('m')
  })
})

describe('StatusCard', () => {
  it('renders the loading card', () => {
    render(<StatusCard kind="loading" t={t} />)
    expect(screen.getByTestId('report-loading')).toHaveTextContent('Bericht wird geladen')
  })

  it('renders the error card with optional retry and message fallback', () => {
    const onRetry = jest.fn()
    const { rerender } = render(<StatusCard kind="error" message="Kaputt" onRetry={onRetry} t={t} />)
    const card = screen.getByRole('alert')
    expect(card).toHaveTextContent('Der Bericht konnte nicht geladen werden.')
    expect(card).toHaveTextContent('Kaputt')
    fireEvent.click(screen.getByRole('button', { name: 'Erneut laden' }))
    expect(onRetry).toHaveBeenCalled()
    expect(screen.getByRole('link', { name: 'Zurück zu den Berichten' })).toHaveAttribute('href', '/reports')
    rerender(<StatusCard kind="error" t={t} />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Bitte versuchen Sie es in einem Moment erneut.')
  })

  it('renders the not-public card with login link (default and custom href)', () => {
    const { rerender } = render(<StatusCard kind="forbidden" t={t} />)
    expect(screen.getByTestId('report-forbidden')).toHaveTextContent('Dieser Bericht ist nicht öffentlich.')
    expect(screen.getByRole('link', { name: 'Anmelden' })).toHaveAttribute('href', '/login')
    rerender(<StatusCard kind="forbidden" loginHref="/login?next=%2Freports%2F1" t={t} />)
    expect(screen.getByRole('link', { name: 'Anmelden' })).toHaveAttribute('href', '/login?next=%2Freports%2F1')
  })
})

describe('layout primitives', () => {
  it('renders section, prose, subheading, note, tooltip box and legend', () => {
    render(
      <ReportSection title="Titel" id="x" aside={<span>Aside</span>}>
        <SubHeading>Sub</SubHeading>
        <Prose>Text</Prose>
        <QuietNote>Note</QuietNote>
        <ChartTooltipBox title="Bin 13" lines={[{ label: 'Modelle', value: '12', swatchClass: 'bg-x' }, { label: 'n', value: '1' }]} />
        <ChartLegend items={[{ label: 'Modelle', swatchClass: 'bg-x' }]} />
      </ReportSection>,
    )
    expect(screen.getByTestId('section-x')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent('Titel')
    expect(screen.getByText('Aside')).toBeInTheDocument()
    expect(screen.getByText('Sub')).toBeInTheDocument()
    expect(screen.getByText('Note')).toBeInTheDocument()
    expect(screen.getByTestId('chart-tooltip')).toHaveTextContent('Bin 13')
    expect(screen.getByTestId('chart-legend')).toHaveTextContent('Modelle')
  })

  it('renders a section without id', () => {
    render(
      <ReportSection title="T">
        <span>c</span>
      </ReportSection>,
    )
    expect(screen.getByText('c')).toBeInTheDocument()
  })
})
