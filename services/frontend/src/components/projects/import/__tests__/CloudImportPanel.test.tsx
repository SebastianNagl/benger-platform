/**
 * Tests for CloudImportPanel — the org-storage cloud import tab body.
 * Covers the org → connection → browse flow, extension gating, the
 * 20-file selection cap, select-mode reporting and immediate-mode import
 * (with history + re-run).
 *
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import {
  CloudImportPanel,
  IMPORTABLE_EXTENSIONS,
  MAX_CLOUD_IMPORT_FILES,
  isImportableKey,
} from '../CloudImportPanel'

const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({
  useToast: () => ({ addToast: mockAddToast }),
}))

jest.mock('@/components/shared/Button', () => ({
  Button: ({ children, onClick, disabled, variant, ...props }: any) => (
    <button
      onClick={onClick}
      disabled={disabled}
      data-variant={variant}
      {...props}
    >
      {children}
    </button>
  ),
}))

jest.mock('@heroicons/react/24/outline', () => ({
  ArrowPathIcon: (props: any) => <svg {...props} />,
  DocumentIcon: (props: any) => <svg {...props} />,
  FolderIcon: (props: any) => <svg {...props} />,
}))

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({
    t: (key: string, vars?: Record<string, any>) => {
      let result = key
      if (vars) {
        result += Object.entries(vars)
          .map(([k, v]) => ` ${k}=${String(v)}`)
          .join('')
      }
      return result
    },
  }),
}))

const mockStartProgress = jest.fn()
const mockUpdateProgress = jest.fn()
const mockCompleteProgress = jest.fn()
jest.mock('@/contexts/ProgressContext', () => ({
  useProgress: () => ({
    startProgress: mockStartProgress,
    updateProgress: mockUpdateProgress,
    completeProgress: mockCompleteProgress,
  }),
}))

let mockOrganizations: any[] = []
jest.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ organizations: mockOrganizations }),
}))

const mockListStorageConnections = jest.fn()
const mockListObjects = jest.fn()
jest.mock('@/lib/api/organizations', () => ({
  organizationsAPI: {
    listStorageConnections: (...args: any[]) =>
      mockListStorageConnections(...args),
    listStorageConnectionObjects: (...args: any[]) => mockListObjects(...args),
  },
}))

const mockRunCloudImportJobs = jest.fn()
const mockListCloudImports = jest.fn()
jest.mock('@/lib/api/projects', () => ({
  projectsAPI: {
    runCloudImportJobs: (...args: any[]) => mockRunCloudImportJobs(...args),
    listCloudImports: (...args: any[]) => mockListCloudImports(...args),
  },
}))

const ORG_A = { id: 'org-a', name: 'orga', display_name: 'Org A' }
const ORG_B = { id: 'org-b', name: 'orgb', display_name: 'Org B' }

const CONN = {
  id: 'conn-1',
  organization_id: 'org-a',
  name: 'Chair bucket',
  endpoint_url: null,
  bucket: 'law-exams',
  prefix: 'imports/',
  region: null,
  use_ssl: true,
  access_key_hint: 'A1B2',
  created_by: null,
  created_at: null,
  updated_at: null,
}

const PAGE = {
  objects: [
    {
      key: 'imports/tasks.json',
      size: 2048,
      last_modified: '2026-08-30T10:00:00Z',
    },
    {
      key: 'imports/photo.png',
      size: 512,
      last_modified: '2026-08-30T10:00:00Z',
    },
  ],
  prefixes: ['imports/2026/'],
  next_token: null,
}

beforeEach(() => {
  jest.clearAllMocks()
  mockOrganizations = [ORG_A, ORG_B]
  mockListStorageConnections.mockResolvedValue([CONN])
  mockListObjects.mockResolvedValue(PAGE)
  mockListCloudImports.mockResolvedValue([])
})

async function selectOrgAndConnection() {
  fireEvent.change(screen.getByTestId('cloud-import-org-select'), {
    target: { value: 'org-a' },
  })
  await waitFor(() =>
    expect(mockListStorageConnections).toHaveBeenCalledWith('org-a')
  )
  // Wait for the connection option to render before selecting it.
  await screen.findByText('Chair bucket (law-exams)')
  fireEvent.change(screen.getByTestId('cloud-import-connection-select'), {
    target: { value: 'conn-1' },
  })
  await waitFor(() => expect(mockListObjects).toHaveBeenCalled())
}

describe('isImportableKey', () => {
  it('accepts every documented extension case-insensitively', () => {
    for (const ext of IMPORTABLE_EXTENSIONS) {
      expect(isImportableKey(`dir/file${ext}`)).toBe(true)
      expect(isImportableKey(`dir/FILE${ext.toUpperCase()}`)).toBe(true)
    }
  })

  it('rejects other extensions', () => {
    expect(isImportableKey('a.png')).toBe(false)
    expect(isImportableKey('a.pdf')).toBe(false)
    expect(isImportableKey('a.json.zip')).toBe(false)
  })
})

describe('CloudImportPanel — pickers', () => {
  it('shows the no-organizations empty state', () => {
    mockOrganizations = []
    render(<CloudImportPanel mode="select" />)
    expect(
      screen.getByText('dataImport.cloud.noOrganizations')
    ).toBeInTheDocument()
    expect(
      screen.queryByTestId('cloud-import-org-select')
    ).not.toBeInTheDocument()
  })

  it('auto-selects a single org and loads its connections', async () => {
    mockOrganizations = [ORG_A]
    render(<CloudImportPanel mode="select" />)
    await waitFor(() =>
      expect(mockListStorageConnections).toHaveBeenCalledWith('org-a')
    )
    expect(screen.getByTestId('cloud-import-org-select')).toHaveValue('org-a')
  })

  it('explains the admin setup when the org has no connections', async () => {
    mockListStorageConnections.mockResolvedValue([])
    render(<CloudImportPanel mode="select" />)
    fireEvent.change(screen.getByTestId('cloud-import-org-select'), {
      target: { value: 'org-a' },
    })
    expect(
      await screen.findByTestId('cloud-import-no-connections')
    ).toHaveTextContent('dataImport.cloud.noConnections')
  })
})

describe('CloudImportPanel — browsing', () => {
  it('lists the connection root with folders and files', async () => {
    render(<CloudImportPanel mode="select" />)
    await selectOrgAndConnection()

    expect(mockListObjects).toHaveBeenCalledWith('org-a', 'conn-1', {
      prefix: 'imports/',
      continuationToken: undefined,
      maxResults: 100,
    })
    expect(
      await screen.findByTestId('cloud-import-folder-2026')
    ).toBeInTheDocument()
    expect(
      screen.getByTestId('cloud-import-object-tasks.json')
    ).toBeInTheDocument()
    expect(
      screen.getByTestId('cloud-import-object-photo.png')
    ).toBeInTheDocument()
  })

  it('disables checkboxes on non-importable extensions', async () => {
    render(<CloudImportPanel mode="select" />)
    await selectOrgAndConnection()

    const jsonRow = await screen.findByTestId('cloud-import-object-tasks.json')
    const pngRow = screen.getByTestId('cloud-import-object-photo.png')
    expect(jsonRow.querySelector('input')).not.toBeDisabled()
    expect(pngRow.querySelector('input')).toBeDisabled()
  })

  it('descends into a folder via its row and back via breadcrumbs', async () => {
    render(<CloudImportPanel mode="select" />)
    await selectOrgAndConnection()

    mockListObjects.mockResolvedValue({
      objects: [],
      prefixes: [],
      next_token: null,
    })
    fireEvent.click(await screen.findByTestId('cloud-import-folder-2026'))
    await waitFor(() =>
      expect(mockListObjects).toHaveBeenLastCalledWith('org-a', 'conn-1', {
        prefix: 'imports/2026/',
        continuationToken: undefined,
        maxResults: 100,
      })
    )

    fireEvent.click(screen.getByTestId('cloud-import-breadcrumb-root'))
    await waitFor(() =>
      expect(mockListObjects).toHaveBeenLastCalledWith('org-a', 'conn-1', {
        prefix: 'imports/',
        continuationToken: undefined,
        maxResults: 100,
      })
    )
  })

  it('pages further results via the load-more button', async () => {
    mockListObjects.mockResolvedValueOnce({ ...PAGE, next_token: 'tok-1' })
    render(<CloudImportPanel mode="select" />)
    await selectOrgAndConnection()

    mockListObjects.mockResolvedValueOnce({
      objects: [
        { key: 'imports/more.csv', size: 1, last_modified: null },
      ],
      prefixes: [],
      next_token: null,
    })
    fireEvent.click(await screen.findByTestId('cloud-import-load-more'))

    await waitFor(() =>
      expect(mockListObjects).toHaveBeenLastCalledWith('org-a', 'conn-1', {
        prefix: 'imports/',
        continuationToken: 'tok-1',
        maxResults: 100,
      })
    )
    // Appended, not replaced.
    expect(
      await screen.findByTestId('cloud-import-object-more.csv')
    ).toBeInTheDocument()
    expect(
      screen.getByTestId('cloud-import-object-tasks.json')
    ).toBeInTheDocument()
  })

  it('shows the browse error text on a failed listing', async () => {
    mockListObjects.mockRejectedValue({
      response: { data: { detail: 'Access denied on bucket' } },
    })
    render(<CloudImportPanel mode="select" />)
    await selectOrgAndConnection()
    expect(
      await screen.findByText('Access denied on bucket')
    ).toBeInTheDocument()
  })
})

describe('CloudImportPanel — select mode', () => {
  it('reports the selection up and shows a summary line', async () => {
    const onSelectionChange = jest.fn()
    render(
      <CloudImportPanel mode="select" onSelectionChange={onSelectionChange} />
    )
    await selectOrgAndConnection()

    const jsonRow = await screen.findByTestId('cloud-import-object-tasks.json')
    fireEvent.click(jsonRow.querySelector('input')!)

    expect(onSelectionChange).toHaveBeenLastCalledWith({
      organizationId: 'org-a',
      connectionId: 'conn-1',
      objectKeys: ['imports/tasks.json'],
    })
    expect(
      screen.getByTestId('cloud-import-selection-summary')
    ).toHaveTextContent('dataImport.cloud.selectionSummary count=1')

    // Unchecking reports the empty selection.
    fireEvent.click(jsonRow.querySelector('input')!)
    expect(onSelectionChange).toHaveBeenLastCalledWith({
      organizationId: 'org-a',
      connectionId: 'conn-1',
      objectKeys: [],
    })
  })

  it('caps the selection at 20 files and shows the hint', async () => {
    const manyKeys = Array.from(
      { length: MAX_CLOUD_IMPORT_FILES },
      (_, i) => `imports/f${i}.json`
    )
    render(
      <CloudImportPanel
        mode="select"
        initialSelection={{
          organizationId: 'org-a',
          connectionId: 'conn-1',
          objectKeys: manyKeys,
        }}
      />
    )
    await waitFor(() =>
      expect(mockListStorageConnections).toHaveBeenCalledWith('org-a')
    )
    await waitFor(() => expect(mockListObjects).toHaveBeenCalled())

    expect(
      screen.getByTestId('cloud-import-selection-summary')
    ).toHaveTextContent(`count=${MAX_CLOUD_IMPORT_FILES}`)
    expect(
      screen.getByText(
        `dataImport.cloud.selectionCapHint max=${MAX_CLOUD_IMPORT_FILES}`
      )
    ).toBeInTheDocument()
    // A further (unchecked) importable file is disabled at the cap.
    const jsonRow = await screen.findByTestId('cloud-import-object-tasks.json')
    expect(jsonRow.querySelector('input')).toBeDisabled()
  })

  it('restores an initial selection (org, connection, keys)', async () => {
    render(
      <CloudImportPanel
        mode="select"
        initialSelection={{
          organizationId: 'org-a',
          connectionId: 'conn-1',
          objectKeys: ['imports/tasks.json'],
        }}
      />
    )
    await waitFor(() => expect(mockListObjects).toHaveBeenCalled())
    expect(screen.getByTestId('cloud-import-org-select')).toHaveValue('org-a')
    expect(
      screen.getByTestId('cloud-import-connection-select')
    ).toHaveValue('conn-1')
    const jsonRow = await screen.findByTestId('cloud-import-object-tasks.json')
    expect(jsonRow.querySelector('input')).toBeChecked()
  })
})

describe('CloudImportPanel — immediate mode', () => {
  it('imports the selection and refreshes history + completion callback', async () => {
    mockRunCloudImportJobs.mockResolvedValue([])
    const onImportComplete = jest.fn()
    render(
      <CloudImportPanel
        mode="immediate"
        projectId="proj-1"
        onImportComplete={onImportComplete}
      />
    )
    await selectOrgAndConnection()

    const jsonRow = await screen.findByTestId('cloud-import-object-tasks.json')
    fireEvent.click(jsonRow.querySelector('input')!)

    const importButton = screen.getByTestId('cloud-import-import-button')
    expect(importButton).not.toBeDisabled()
    fireEvent.click(importButton)

    await waitFor(() =>
      expect(mockRunCloudImportJobs).toHaveBeenCalledWith(
        'proj-1',
        {
          connection_id: 'conn-1',
          object_keys: ['imports/tasks.json'],
        },
        expect.anything()
      )
    )
    await waitFor(() =>
      expect(mockAddToast).toHaveBeenCalledWith(
        'dataImport.cloud.importSuccess',
        'success'
      )
    )
    expect(mockStartProgress).toHaveBeenCalled()
    expect(mockCompleteProgress).toHaveBeenCalledWith(
      expect.any(String),
      'success'
    )
    // History fetched initially + after the import.
    expect(mockListCloudImports).toHaveBeenCalledTimes(2)
    expect(onImportComplete).toHaveBeenCalled()
    // Selection cleared after a successful import.
    expect(
      screen.getByTestId('cloud-import-selection-summary')
    ).toHaveTextContent('count=0')
  })

  it('disables the import button without a selection', async () => {
    render(<CloudImportPanel mode="immediate" projectId="proj-1" />)
    await selectOrgAndConnection()
    expect(
      await screen.findByTestId('cloud-import-import-button')
    ).toBeDisabled()
  })

  it('toasts the aggregate error when the import fails', async () => {
    mockRunCloudImportJobs.mockRejectedValue(
      new Error('imports/tasks.json: bad payload')
    )
    render(<CloudImportPanel mode="immediate" projectId="proj-1" />)
    await selectOrgAndConnection()

    const jsonRow = await screen.findByTestId('cloud-import-object-tasks.json')
    fireEvent.click(jsonRow.querySelector('input')!)
    fireEvent.click(screen.getByTestId('cloud-import-import-button'))

    await waitFor(() =>
      expect(mockAddToast).toHaveBeenCalledWith(
        'dataImport.cloud.importFailedWithReason reason=imports/tasks.json: bad payload',
        'error'
      )
    )
    expect(mockCompleteProgress).toHaveBeenCalledWith(
      expect.any(String),
      'error'
    )
  })

  it('renders the history and re-runs a row via its connection name', async () => {
    mockListCloudImports.mockResolvedValue([
      {
        job_id: 'job-1',
        project_id: 'proj-1',
        format: 'json',
        status: 'completed',
        progress: 100,
        byte_size: 10,
        error_message: null,
        result: null,
        created_at: '2026-08-30T10:00:00Z',
        updated_at: null,
        expires_at: null,
        object_key: 'imports/tasks.json',
        connection_name: 'Chair bucket',
      },
      {
        job_id: 'job-2',
        project_id: 'proj-1',
        format: 'json',
        status: 'failed',
        progress: 0,
        byte_size: null,
        error_message: 'boom',
        result: null,
        created_at: '2026-08-29T10:00:00Z',
        updated_at: null,
        expires_at: null,
        object_key: 'imports/old.json',
        connection_name: 'Deleted connection',
      },
    ])
    mockRunCloudImportJobs.mockResolvedValue([])
    render(<CloudImportPanel mode="immediate" projectId="proj-1" />)
    await selectOrgAndConnection()

    const history = await screen.findByTestId('cloud-import-history')
    expect(history).toHaveTextContent('tasks.json')
    expect(history).toHaveTextContent('dataImport.cloud.status.completed')
    expect(history).toHaveTextContent('dataImport.cloud.status.failed')

    // Row whose connection name matches a loaded connection can be re-run.
    fireEvent.click(screen.getByTestId('cloud-import-rerun-job-1'))
    await waitFor(() =>
      expect(mockRunCloudImportJobs).toHaveBeenCalledWith(
        'proj-1',
        {
          connection_id: 'conn-1',
          object_keys: ['imports/tasks.json'],
        },
        expect.anything()
      )
    )

    // Row whose connection is gone stays disabled.
    expect(screen.getByTestId('cloud-import-rerun-job-2')).toBeDisabled()
  })
})
