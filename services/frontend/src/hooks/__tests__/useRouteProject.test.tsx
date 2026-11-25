/**
 * @jest-environment jsdom
 *
 * useRouteProject: a project page only ever sees the project its URL names,
 * never the one the store still holds from before, and "not found" only
 * after the API refused the read.
 */
import { act, renderHook, waitFor } from '@testing-library/react'

import { useRouteProject } from '../useRouteProject'

const mockFetchProject = jest.fn()
let mockCurrentProject: { id: string; title: string } | null = null
jest.mock('@/stores/projectStore', () => ({
  useProjectStore: () => ({
    currentProject: mockCurrentProject,
    fetchProject: mockFetchProject,
  }),
}))

beforeEach(() => {
  jest.clearAllMocks()
  mockCurrentProject = null
  mockFetchProject.mockReturnValue(new Promise(() => {}))
})

describe('useRouteProject', () => {
  it('hides a different project held in the store and reads this one', () => {
    mockCurrentProject = { id: 'p-old', title: 'Vorher' }
    const { result } = renderHook(() => useRouteProject('p1'))
    expect(result.current).toEqual({ project: null, notFound: false })
    expect(mockFetchProject).toHaveBeenCalledWith('p1', { shared: true })
  })

  it('returns the held project of this route without a read', () => {
    mockCurrentProject = { id: 'p1', title: 'Eins' }
    const { result } = renderHook(() => useRouteProject('p1'))
    expect(result.current.project?.title).toBe('Eins')
    expect(mockFetchProject).not.toHaveBeenCalled()
  })

  it('with refresh, reads once per id while showing the held copy', () => {
    mockCurrentProject = { id: 'p1', title: 'Eins' }
    const { result, rerender } = renderHook(() =>
      useRouteProject('p1', { refresh: true }),
    )
    rerender()
    expect(result.current.project?.title).toBe('Eins')
    expect(mockFetchProject).toHaveBeenCalledTimes(1)
  })

  it('says "not found" only after the read was refused', async () => {
    let refuse!: (value: null) => void
    mockFetchProject.mockReturnValue(
      new Promise<null>((resolve) => {
        refuse = resolve
      }),
    )
    const { result } = renderHook(() => useRouteProject('p1'))
    expect(result.current.notFound).toBe(false)
    await act(async () => {
      refuse(null)
    })
    await waitFor(() => expect(result.current.notFound).toBe(true))
  })

  it('reads nothing without an id', () => {
    const { result } = renderHook(() => useRouteProject(null))
    expect(result.current).toEqual({ project: null, notFound: false })
    expect(mockFetchProject).not.toHaveBeenCalled()
  })
})
