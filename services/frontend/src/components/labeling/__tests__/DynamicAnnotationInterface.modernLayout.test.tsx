/**
 * @jest-environment jsdom
 *
 * Modern exam layout seam tests for DynamicAnnotationInterface.
 *
 * The critical regression here: field data must survive submission even when
 * the modern layout never renders a field's component (user placed it 'none',
 * or a buggy shell skips a node). Server-loaded initialValues and the
 * whole-form localStorage draft seed the annotation Maps mount-independently,
 * and the submit merge reads only those Maps.
 */

import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

import { registerComponent } from '@/lib/labelConfig/registry'
import type {
  ModernExamLayoutProps,
} from '@/lib/labelConfig/examLayout'

const EDITION_KEY = 'NEXT_PUBLIC_BENGER_EDITION'
const originalEdition = process.env[EDITION_KEY]

let mockSlots: Record<string, unknown> = {}
let mockUser: any = null

jest.mock('@/lib/extensions/slots', () => ({
  useSlot: (name: string) => mockSlots[name] ?? null,
  hasSlot: (name: string) => !!mockSlots[name],
  registerSlot: (name: string, component: unknown) => {
    mockSlots[name] = component
  },
}))
jest.mock('@/contexts/AuthContext', () => ({
  useOptionalAuth: () => ({ user: mockUser }),
}))
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (key: string) => key, locale: 'en' }),
}))

import { DynamicAnnotationInterface } from '../DynamicAnnotationInterface'

// Register lightweight stand-ins for the four extended exam components (the
// real ones live in benger-extended). Registration is file-scoped: each jest
// module registry starts from the built-in core set.
const fieldRenderCounts: Record<string, number> = {}
for (const tag of ['Angabe', 'Notizen', 'Gliederung', 'Loesung']) {
  registerComponent(tag, {
    component: ({ config }: any) => {
      const name = config.props.name || config.name
      fieldRenderCounts[name] = (fieldRenderCounts[name] || 0) + 1
      return <div data-testid={`field-${name}`} />
    },
    category: 'control',
  })
}

const EXAM_CONFIG = `
  <View>
    <Header value="Angabe"/>
    <Angabe name="angabe" toName="sachverhalt"/>
    <Header value="Notizen"/>
    <Notizen name="notizen" toName="sachverhalt"/>
    <Header value="Gliederung"/>
    <Gliederung name="gliederung" toName="sachverhalt"/>
    <Header value="Loesung"/>
    <Loesung name="loesung" toName="sachverhalt"/>
  </View>
`

const MODERN_PREFS = {
  mode: 'modern',
  case_position: 'left',
  notes_position: 'right',
  outline_position: 'none',
}

const INITIAL_VALUES = [
  {
    from_name: 'notizen',
    to_name: 'sachverhalt',
    type: 'notizen',
    value: { markdown: 'saved notes from a previous session' },
  },
  {
    from_name: 'gliederung',
    to_name: 'sachverhalt',
    type: 'gliederung',
    value: { markdown: 'A. Anspruch entstanden' },
  },
  {
    from_name: 'loesung',
    to_name: 'sachverhalt',
    type: 'loesung',
    value: { markdown: 'Lösungstext' },
  },
]

/** Shell that deliberately renders ONLY the Loesung node — the worst case a
 *  layout can do to the other fields. */
const SubsetShell = ({ parsedConfig, renderComponent }: ModernExamLayoutProps) => (
  <div data-testid="modern-shell">
    {parsedConfig.children
      .filter((child) => child.type === 'Loesung')
      .map((child, i) => renderComponent(child, `main_${i}`))}
  </div>
)

const recordShell = jest.fn<void, [ModernExamLayoutProps]>()
const lastSlotProps = (): ModernExamLayoutProps | null =>
  recordShell.mock.calls.length ? recordShell.mock.calls[recordShell.mock.calls.length - 1][0] : null
const RecordingShell = (props: ModernExamLayoutProps) => {
  recordShell(props)
  return <div data-testid="modern-shell" />
}

function renderInterface(overrides: Record<string, unknown> = {}) {
  const onSubmit = jest.fn()
  const utils = render(
    <DynamicAnnotationInterface
      labelConfig={EXAM_CONFIG}
      taskData={{ sachverhalt: 'Der Sachverhalt.' }}
      taskId="task-1"
      initialValues={INITIAL_VALUES as any}
      onSubmit={onSubmit}
      {...overrides}
    />
  )
  return { onSubmit, ...utils }
}

describe('DynamicAnnotationInterface modern layout seam', () => {
  beforeEach(() => {
    process.env[EDITION_KEY] = 'extended'
    mockSlots = { ModernExamLayout: RecordingShell }
    mockUser = { id: 'u1', exam_layout_prefs: MODERN_PREFS }
    recordShell.mockClear()
    localStorage.clear()
    for (const key of Object.keys(fieldRenderCounts)) delete fieldRenderCounts[key]
  })
  afterEach(() => {
    if (originalEdition === undefined) {
      delete process.env[EDITION_KEY]
    } else {
      process.env[EDITION_KEY] = originalEdition
    }
  })

  it('stays classic without the allowModernLayout host opt-in (review contract)', async () => {
    renderInterface()
    expect(await screen.findByTestId('field-loesung')).toBeInTheDocument()
    expect(screen.getByTestId('field-notizen')).toBeInTheDocument()
    expect(screen.queryByTestId('modern-shell')).not.toBeInTheDocument()
  })

  it('stays classic when the slot is unregistered or the preference is classic', async () => {
    mockSlots = {}
    const first = renderInterface({ allowModernLayout: true })
    expect(await first.findByTestId('field-loesung')).toBeInTheDocument()
    expect(first.queryByTestId('modern-shell')).not.toBeInTheDocument()
    first.unmount()

    mockSlots = { ModernExamLayout: RecordingShell }
    mockUser = { id: 'u1', exam_layout_prefs: { ...MODERN_PREFS, mode: 'classic' } }
    const second = renderInterface({ allowModernLayout: true })
    expect(await second.findByTestId('field-loesung')).toBeInTheDocument()
    expect(second.queryByTestId('modern-shell')).not.toBeInTheDocument()
  })

  it('hands the slot the parsed tree, the live renderer, and the prefs', async () => {
    renderInterface({ allowModernLayout: true, readOnly: false })

    expect(await screen.findByTestId('modern-shell')).toBeInTheDocument()
    expect(lastSlotProps()).not.toBeNull()
    expect(lastSlotProps()!.parsedConfig.type).toBe('View')
    expect(typeof lastSlotProps()!.renderComponent).toBe('function')
    expect(lastSlotProps()!.prefs).toEqual(MODERN_PREFS)
    expect(lastSlotProps()!.taskId).toBe('task-1')
    // The platform action bar renders below the slot in the modern branch too.
    expect(screen.getByText('annotation.interface.submit')).toBeInTheDocument()
  })

  it('renderComponent handed to the slot renders real registered fields', async () => {
    mockSlots = { ModernExamLayout: SubsetShell }
    renderInterface({ allowModernLayout: true })

    expect(await screen.findByTestId('field-loesung')).toBeInTheDocument()
    expect(fieldRenderCounts['loesung']).toBeGreaterThanOrEqual(1)
    // The subset shell never rendered the others.
    expect(screen.queryByTestId('field-notizen')).not.toBeInTheDocument()
    expect(screen.queryByTestId('field-gliederung')).not.toBeInTheDocument()
  })

  it('REGRESSION: never-rendered fields still submit their initialValues', async () => {
    mockSlots = { ModernExamLayout: SubsetShell }
    const { onSubmit } = renderInterface({ allowModernLayout: true })

    await screen.findByTestId('field-loesung')
    fireEvent.click(screen.getByText('annotation.interface.submit'))

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
    const submitted = onSubmit.mock.calls[0][0] as any[]
    const byName = Object.fromEntries(submitted.map((a) => [a.from_name, a]))

    // notizen and gliederung components never mounted — their server-loaded
    // annotations must be submitted verbatim regardless.
    expect(byName.notizen).toEqual(INITIAL_VALUES[0])
    expect(byName.gliederung).toEqual(INITIAL_VALUES[1])
    expect(byName.loesung).toEqual(INITIAL_VALUES[2])
  })

  it('REGRESSION: never-rendered fields still submit whole-form draft values', async () => {
    // Seed the useAutoSave draft for task-2: content that exists ONLY in the
    // localStorage draft (e.g. typed seconds before a reload).
    localStorage.setItem(
      'benger_draft_task-2',
      JSON.stringify({
        taskId: 'task-2',
        annotations: [
          {
            from_name: 'notizen',
            to_name: 'sachverhalt',
            type: 'notizen',
            value: { markdown: 'draft-only notes' },
          },
        ],
        componentValues: { notizen: { markdown: 'draft-only notes' } },
        savedAt: 1700000000000,
        leadTime: 5,
      })
    )
    mockSlots = { ModernExamLayout: SubsetShell }
    const { onSubmit } = renderInterface({
      allowModernLayout: true,
      taskId: 'task-2',
      initialValues: undefined,
    })

    await screen.findByTestId('field-loesung')
    await waitFor(() =>
      expect(screen.getByText('annotation.interface.submit')).not.toBeDisabled()
    )
    fireEvent.click(screen.getByText('annotation.interface.submit'))

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
    const submitted = onSubmit.mock.calls[0][0] as any[]
    const notizen = submitted.find((a) => a.from_name === 'notizen')
    expect(notizen).toBeDefined()
    expect(notizen.value).toEqual({ markdown: 'draft-only notes' })
  })
})
