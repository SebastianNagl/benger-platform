/**
 * @jest-environment jsdom
 *
 * Structure-scoped generation view: the task matrix gains a prompt-structure
 * selector (mirroring the evaluations page's per-method scoping) —
 *   - rendered only when the project has >1 prompt structure
 *   - options labeled with the structure's display name + key
 *   - selecting one refetches /task-status with ?structure_key=<key>
 *   - hidden for single-structure projects (filter would be a no-op)
 */
import '@testing-library/jest-dom'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { GenerationTaskList } from '../GenerationTaskList'

// Minimal WebSocket stub (no reconnect noise in jsdom).
class MockWebSocket {
  onopen: any = null
  onmessage: any = null
  onerror: any = null
  onclose: any = null
  constructor(public url: string) {}
  send() {}
  close() {}
}
global.WebSocket = jest.fn((url: string) => new MockWebSocket(url)) as any

// Native-select stand-in for the shared Radix-style Select so userEvent can
// drive it without portal/pointer plumbing.
jest.mock('@/components/shared/Select', () => {
  const React = jest.requireActual('react')
  return {
    Select: ({ value, onValueChange, children }: any) => {
      const options: any[] = []
      const walk = (node: any) => {
        React.Children.forEach(node?.props?.children ?? node, (child: any) => {
          if (!child || typeof child !== 'object') return
          if (child.props?.value !== undefined && child.type?.displayName !== 'SelectValue') {
            options.push(child)
          }
          if (child.props?.children) walk(child)
        })
      }
      walk({ props: { children } })
      return (
        <select
          data-testid="structure-or-status-select"
          value={value}
          onChange={(e) => onValueChange(e.target.value)}
        >
          {options.map((o: any, i: number) => (
            <option key={i} value={o.props.value}>
              {typeof o.props.children === 'string' ? o.props.children : ''}
            </option>
          ))}
        </select>
      )
    },
    SelectTrigger: ({ children }: any) => <>{children}</>,
    SelectValue: () => null,
    SelectContent: ({ children }: any) => <>{children}</>,
    SelectItem: ({ value, children }: any) => <option value={value}>{children}</option>,
  }
})

const mockGet = jest.fn()
jest.mock('@/lib/api/client', () => ({
  apiClient: { get: (...args: any[]) => mockGet(...args) },
  getApiUrl: () => 'http://localhost:8001',
}))

jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'u1', is_superadmin: true } }),
}))

jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: jest.fn() }),
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, fallback?: any) =>
      typeof fallback === 'string' ? fallback : key,
  }),
}))

const taskStatusResponse = (structures: string[]) => ({
  tasks: [
    {
      id: 'task-1',
      data: { text: 'Aufgabe 1' },
      created_at: '2026-01-01',
      generation_status: {
        'gpt-4o': structures.map((s) => ({
          task_id: 'task-1',
          model_id: 'gpt-4o',
          structure_key: s,
          status: 'completed',
          generation_id: `gen-${s}`,
          generated_at: null,
          error_message: null,
          result_preview: null,
        })),
      },
    },
  ],
  total: 1,
  page: 1,
  page_size: 50,
  total_pages: 1,
  models: ['gpt-4o'],
  structures,
})

const projectResponse = {
  id: 'p1',
  title: 'LEXam Project',
  generation_config: {
    prompt_structures: {
      fallloesung: { name: 'Falllösung' },
      'lexam-open': { name: 'LEXam Open (DE)' },
    },
    selected_configuration: { models: ['gpt-4o'] },
  },
}

function mockApi(structures: string[]) {
  mockGet.mockImplementation((url: string) => {
    if (url.includes('/task-status')) {
      return Promise.resolve(taskStatusResponse(structures))
    }
    if (url.startsWith('/projects/')) {
      return Promise.resolve(projectResponse)
    }
    return Promise.resolve({})
  })
}

beforeEach(() => {
  mockGet.mockReset()
})

// The FilterToolbar renders its fields only after the filter toggle is
// opened (filterPanelVisible = hasFilterFields && showFilters).
async function openFilterPanel(user: ReturnType<typeof userEvent.setup>) {
  const toggle = await screen.findByText('common.filters.filters')
  await user.click(toggle)
}

describe('GenerationTaskList structure filter', () => {
  it('renders the selector with display-name labels when >1 structure', async () => {
    mockApi(['fallloesung', 'lexam-open'])
    const user = userEvent.setup()
    render(<GenerationTaskList projectId="p1" />)
    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith(expect.stringContaining('/task-status'))
    )
    await openFilterPanel(user)
    expect(await screen.findByText('LEXam Open (DE) (lexam-open)')).toBeInTheDocument()
    expect(screen.getByText('Falllösung (fallloesung)')).toBeInTheDocument()
  })

  it('refetches with structure_key when a structure is chosen', async () => {
    mockApi(['fallloesung', 'lexam-open'])
    const user = userEvent.setup()
    render(<GenerationTaskList projectId="p1" />)
    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith(expect.stringContaining('/task-status'))
    )
    await openFilterPanel(user)
    await screen.findByText('LEXam Open (DE) (lexam-open)')

    const selects = screen.getAllByTestId('structure-or-status-select')
    const structureSelect = selects.find((s) =>
      [...s.querySelectorAll('option')].some((o) => o.value === 'lexam-open')
    ) as HTMLSelectElement
    await user.selectOptions(structureSelect, 'lexam-open')

    await waitFor(() => {
      const calls = mockGet.mock.calls.map((c) => c[0])
      expect(
        calls.some(
          (u: string) =>
            u.includes('/task-status') && u.includes('structure_key=lexam-open')
        )
      ).toBe(true)
    })
  })

  it('hides the selector for single-structure projects', async () => {
    mockApi(['fallloesung'])
    const user = userEvent.setup()
    render(<GenerationTaskList projectId="p1" />)
    await waitFor(() =>
      expect(mockGet).toHaveBeenCalledWith(expect.stringContaining('/task-status'))
    )
    await openFilterPanel(user)
    expect(screen.queryByText('Falllösung (fallloesung)')).not.toBeInTheDocument()
  })
})
