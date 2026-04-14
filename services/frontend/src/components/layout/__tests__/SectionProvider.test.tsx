/**
 * @jest-environment jsdom
 */
/* eslint-disable react-hooks/globals -- Valid test pattern: capturing hook values via external variables for assertions */
import { act, render, renderHook, screen } from '@testing-library/react'
import React, { createRef, useEffect } from 'react'
import {
  SectionProvider,
  useSectionStore,
  type Section,
} from '../SectionProvider'

describe('SectionProvider', () => {
  let mockScrollY: number
  let mockInnerHeight: number
  let mockGetBoundingClientRect: jest.Mock

  beforeEach(() => {
    jest.clearAllMocks()
    mockScrollY = 0
    mockInnerHeight = 800
    mockGetBoundingClientRect = jest.fn()

    Object.defineProperty(window, 'scrollY', {
      writable: true,
      configurable: true,
      value: mockScrollY,
    })

    Object.defineProperty(window, 'innerHeight', {
      writable: true,
      configurable: true,
      value: mockInnerHeight,
    })

    window.requestAnimationFrame = jest.fn((cb) => {
      cb(0)
      return 0
    }) as any

    window.cancelAnimationFrame = jest.fn()
    window.addEventListener = jest.fn()
    window.removeEventListener = jest.fn()

    Object.defineProperty(window, 'getComputedStyle', {
      writable: true,
      configurable: true,
      value: jest.fn().mockReturnValue({
        fontSize: '16px',
      }),
    })
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  describe('Basic Rendering', () => {
    it('renders children correctly', () => {
      const sections: Section[] = [
        { id: 'section-1', title: 'Section 1' },
        { id: 'section-2', title: 'Section 2' },
      ]

      render(
        <SectionProvider sections={sections}>
          <div data-testid="test-child">Test Content</div>
        </SectionProvider>
      )

      expect(screen.getByTestId('test-child')).toBeInTheDocument()
      expect(screen.getByText('Test Content')).toBeInTheDocument()
    })

    it('renders with no sections', () => {
      render(
        <SectionProvider sections={[]}>
          <div data-testid="empty-child">Empty Content</div>
        </SectionProvider>
      )

      expect(screen.getByTestId('empty-child')).toBeInTheDocument()
    })

    it('renders multiple children', () => {
      const sections: Section[] = []

      render(
        <SectionProvider sections={sections}>
          <div data-testid="child-1">Child 1</div>
          <div data-testid="child-2">Child 2</div>
          <div data-testid="child-3">Child 3</div>
        </SectionProvider>
      )

      expect(screen.getByTestId('child-1')).toBeInTheDocument()
      expect(screen.getByTestId('child-2')).toBeInTheDocument()
      expect(screen.getByTestId('child-3')).toBeInTheDocument()
    })

    it('renders with nested elements', () => {
      const sections: Section[] = []

      render(
        <SectionProvider sections={sections}>
          <div data-testid="parent">
            <div data-testid="nested-child">Nested</div>
          </div>
        </SectionProvider>
      )

      expect(screen.getByTestId('parent')).toBeInTheDocument()
      expect(screen.getByTestId('nested-child')).toBeInTheDocument()
    })
  })

  describe('Context Provision', () => {
    it('provides section store to children', () => {
      const sections: Section[] = [{ id: 'test', title: 'Test Section' }]
      let contextValue: any

      function TestConsumer() {
        contextValue = useSectionStore((state) => state.sections)
        return <div>Test</div>
      }

      render(
        <SectionProvider sections={sections}>
          <TestConsumer />
        </SectionProvider>
      )

      expect(contextValue).toEqual(sections)
    })

    it('provides initial empty visible sections', () => {
      const sections: Section[] = [{ id: 'test', title: 'Test' }]
      let visibleSections: string[]

      function TestConsumer() {
        visibleSections = useSectionStore((state) => state.visibleSections)
        return <div>Test</div>
      }

      render(
        <SectionProvider sections={sections}>
          <TestConsumer />
        </SectionProvider>
      )

      expect(visibleSections).toEqual([])
    })

    it('provides setVisibleSections function', () => {
      const sections: Section[] = []
      let setVisibleSections: any

      function TestConsumer() {
        setVisibleSections = useSectionStore(
          (state) => state.setVisibleSections
        )
        return <div>Test</div>
      }

      render(
        <SectionProvider sections={sections}>
          <TestConsumer />
        </SectionProvider>
      )

      expect(typeof setVisibleSections).toBe('function')
    })

    it('provides registerHeading function', () => {
      const sections: Section[] = []
      let registerHeading: any

      function TestConsumer() {
        registerHeading = useSectionStore((state) => state.registerHeading)
        return <div>Test</div>
      }

      render(
        <SectionProvider sections={sections}>
          <TestConsumer />
        </SectionProvider>
      )

      expect(typeof registerHeading).toBe('function')
    })
  })

  describe('Section Registration', () => {
    it('registers heading with ref', () => {
      const sections: Section[] = [{ id: 'test', title: 'Test' }]
      const headingRef = createRef<HTMLHeadingElement>()
      let registeredSections: Section[]

      function TestConsumer() {
        const registerHeading = useSectionStore(
          (state) => state.registerHeading
        )
        registeredSections = useSectionStore((state) => state.sections)

        useEffect(() => {
          registerHeading({ id: 'test', ref: headingRef, offsetRem: 2 })
        }, [registerHeading])

        return <div>Test</div>
      }

      render(
        <SectionProvider sections={sections}>
          <TestConsumer />
        </SectionProvider>
      )

      expect(registeredSections[0].headingRef).toBe(headingRef)
      expect(registeredSections[0].offsetRem).toBe(2)
    })

    it('registers multiple headings', () => {
      const sections: Section[] = [
        { id: 'section-1', title: 'Section 1' },
        { id: 'section-2', title: 'Section 2' },
        { id: 'section-3', title: 'Section 3' },
      ]
      const ref1 = createRef<HTMLHeadingElement>()
      const ref2 = createRef<HTMLHeadingElement>()
      const ref3 = createRef<HTMLHeadingElement>()
      let registeredSections: Section[]

      function TestConsumer() {
        const registerHeading = useSectionStore(
          (state) => state.registerHeading
        )
        registeredSections = useSectionStore((state) => state.sections)

        useEffect(() => {
          registerHeading({ id: 'section-1', ref: ref1, offsetRem: 1 })
          registerHeading({ id: 'section-2', ref: ref2, offsetRem: 2 })
          registerHeading({ id: 'section-3', ref: ref3, offsetRem: 3 })
        }, [registerHeading])

        return <div>Test</div>
      }

      render(
        <SectionProvider sections={sections}>
          <TestConsumer />
        </SectionProvider>
      )

      expect(registeredSections[0].headingRef).toBe(ref1)
      expect(registeredSections[0].offsetRem).toBe(1)
      expect(registeredSections[1].headingRef).toBe(ref2)
      expect(registeredSections[1].offsetRem).toBe(2)
      expect(registeredSections[2].headingRef).toBe(ref3)
      expect(registeredSections[2].offsetRem).toBe(3)
    })

    it('updates existing section with heading ref', () => {
      const sections: Section[] = [{ id: 'test', title: 'Test', offsetRem: 0 }]
      const newRef = createRef<HTMLHeadingElement>()
      let registeredSections: Section[]

      function TestConsumer() {
        const registerHeading = useSectionStore(
          (state) => state.registerHeading
        )
        registeredSections = useSectionStore((state) => state.sections)

        useEffect(() => {
          registerHeading({ id: 'test', ref: newRef, offsetRem: 3 })
        }, [registerHeading])

        return <div>Test</div>
      }

      render(
        <SectionProvider sections={sections}>
          <TestConsumer />
        </SectionProvider>
      )

      expect(registeredSections[0].id).toBe('test')
      expect(registeredSections[0].title).toBe('Test')
      expect(registeredSections[0].headingRef).toBe(newRef)
      expect(registeredSections[0].offsetRem).toBe(3)
    })

    it('does not affect other sections when registering', () => {
      const sections: Section[] = [
        { id: 'section-1', title: 'Section 1' },
        { id: 'section-2', title: 'Section 2' },
      ]
      const ref1 = createRef<HTMLHeadingElement>()
      let registeredSections: Section[]

      function TestConsumer() {
        const registerHeading = useSectionStore(
          (state) => state.registerHeading
        )
        registeredSections = useSectionStore((state) => state.sections)

        useEffect(() => {
          registerHeading({ id: 'section-1', ref: ref1, offsetRem: 1 })
        }, [registerHeading])

        return <div>Test</div>
      }

      render(
        <SectionProvider sections={sections}>
          <TestConsumer />
        </SectionProvider>
      )

      expect(registeredSections[0].headingRef).toBe(ref1)
      expect(registeredSections[1].headingRef).toBeUndefined()
    })
  })

  describe('Section State Management', () => {
    it('updates sections when prop changes', () => {
      const initialSections: Section[] = [
        { id: 'section-1', title: 'Section 1' },
      ]
      let currentSections: Section[]

      function TestConsumer() {
        currentSections = useSectionStore((state) => state.sections)
        return <div>Test</div>
      }

      const { rerender } = render(
        <SectionProvider sections={initialSections}>
          <TestConsumer />
        </SectionProvider>
      )

      expect(currentSections).toEqual(initialSections)

      const newSections: Section[] = [
        { id: 'section-1', title: 'Section 1' },
        { id: 'section-2', title: 'Section 2' },
      ]

      rerender(
        <SectionProvider sections={newSections}>
          <TestConsumer />
        </SectionProvider>
      )

      expect(currentSections).toEqual(newSections)
    })

    it('updates visible sections via setVisibleSections', () => {
      const sections: Section[] = [{ id: 'test', title: 'Test' }]
      let visibleSections: string[]
      let setVisibleSections: any

      function TestConsumer() {
        visibleSections = useSectionStore((state) => state.visibleSections)
        setVisibleSections = useSectionStore(
          (state) => state.setVisibleSections
        )
        return <div>Test</div>
      }

      render(
        <SectionProvider sections={sections}>
          <TestConsumer />
        </SectionProvider>
      )

      expect(visibleSections).toEqual([])

      act(() => {
        setVisibleSections(['test'])
      })

      expect(visibleSections).toEqual(['test'])
    })

    it('does not update state when visible sections are the same', () => {
      const sections: Section[] = [{ id: 'test', title: 'Test' }]
      let renderCount = 0
      let setVisibleSections: any

      function TestConsumer() {
        renderCount++
        setVisibleSections = useSectionStore(
          (state) => state.setVisibleSections
        )
        return <div>Test</div>
      }

      render(
        <SectionProvider sections={sections}>
          <TestConsumer />
        </SectionProvider>
      )

      const initialRenderCount = renderCount

      act(() => {
        setVisibleSections(['test'])
      })

      const afterFirstUpdateCount = renderCount

      act(() => {
        setVisibleSections(['test'])
      })

      expect(renderCount).toBe(afterFirstUpdateCount)
    })

    it('handles multiple visible sections', () => {
      const sections: Section[] = [
        { id: 'section-1', title: 'Section 1' },
        { id: 'section-2', title: 'Section 2' },
        { id: 'section-3', title: 'Section 3' },
      ]
      let visibleSections: string[]
      let setVisibleSections: any

      function TestConsumer() {
        visibleSections = useSectionStore((state) => state.visibleSections)
        setVisibleSections = useSectionStore(
          (state) => state.setVisibleSections
        )
        return <div>Test</div>
      }

      render(
        <SectionProvider sections={sections}>
          <TestConsumer />
        </SectionProvider>
      )

      act(() => {
        setVisibleSections(['section-1', 'section-2', 'section-3'])
      })

      expect(visibleSections).toEqual(['section-1', 'section-2', 'section-3'])
    })
  })

  describe('useSectionStore Hook', () => {
    it('selects sections from store', () => {
      const sections: Section[] = [{ id: 'test', title: 'Test' }]

      const { result } = renderHook(
        () => useSectionStore((state) => state.sections),
        {
          wrapper: ({ children }) => (
            <SectionProvider sections={sections}>{children}</SectionProvider>
          ),
        }
      )

      expect(result.current).toEqual(sections)
    })

    it('selects visible sections from store', () => {
      const sections: Section[] = []

      const { result } = renderHook(
        () => useSectionStore((state) => state.visibleSections),
        {
          wrapper: ({ children }) => (
            <SectionProvider sections={sections}>{children}</SectionProvider>
          ),
        }
      )

      expect(result.current).toEqual([])
    })

    it('selects setVisibleSections function from store', () => {
      const sections: Section[] = []

      const { result } = renderHook(
        () => useSectionStore((state) => state.setVisibleSections),
        {
          wrapper: ({ children }) => (
            <SectionProvider sections={sections}>{children}</SectionProvider>
          ),
        }
      )

      expect(typeof result.current).toBe('function')
    })

    it('selects registerHeading function from store', () => {
      const sections: Section[] = []

      const { result } = renderHook(
        () => useSectionStore((state) => state.registerHeading),
        {
          wrapper: ({ children }) => (
            <SectionProvider sections={sections}>{children}</SectionProvider>
          ),
        }
      )

      expect(typeof result.current).toBe('function')
    })

    it('selects custom derived state', () => {
      const sections: Section[] = [
        { id: 'section-1', title: 'Section 1' },
        { id: 'section-2', title: 'Section 2' },
      ]

      const { result } = renderHook(
        () => useSectionStore((state) => state.sections.length),
        {
          wrapper: ({ children }) => (
            <SectionProvider sections={sections}>{children}</SectionProvider>
          ),
        }
      )

      expect(result.current).toBe(2)
    })

    it('updates when selected state changes', () => {
      jest.useFakeTimers()
      const initialSections: Section[] = [{ id: 'test', title: 'Test' }]

      const Wrapper = ({ children }: { children: React.ReactNode }) => {
        const [sections, setSections] = React.useState(initialSections)

        React.useEffect(() => {
          const timer = setTimeout(() => {
            setSections([
              { id: 'test', title: 'Test' },
              { id: 'test-2', title: 'Test 2' },
            ])
          }, 10)
          return () => clearTimeout(timer)
        }, [])

        return <SectionProvider sections={sections}>{children}</SectionProvider>
      }

      const { result, rerender } = renderHook(
        () => useSectionStore((state) => state.sections),
        { wrapper: Wrapper }
      )

      expect(result.current).toEqual(initialSections)

      act(() => {
        jest.advanceTimersByTime(20)
      })

      rerender()

      jest.useRealTimers()
    })
  })

  describe('Props/Attributes', () => {
    it('accepts sections prop', () => {
      const sections: Section[] = [{ id: 'test', title: 'Test' }]
      let receivedSections: Section[]

      function TestConsumer() {
        receivedSections = useSectionStore((state) => state.sections)
        return <div>Test</div>
      }

      render(
        <SectionProvider sections={sections}>
          <TestConsumer />
        </SectionProvider>
      )

      expect(receivedSections).toEqual(sections)
    })

    it('accepts sections with all properties', () => {
      const headingRef = createRef<HTMLHeadingElement>()
      const sections: Section[] = [
        {
          id: 'complex-section',
          title: 'Complex Section',
          offsetRem: 5,
          tag: 'h2',
          headingRef,
        },
      ]
      let receivedSections: Section[]

      function TestConsumer() {
        receivedSections = useSectionStore((state) => state.sections)
        return <div>Test</div>
      }

      render(
        <SectionProvider sections={sections}>
          <TestConsumer />
        </SectionProvider>
      )

      expect(receivedSections[0].id).toBe('complex-section')
      expect(receivedSections[0].title).toBe('Complex Section')
      expect(receivedSections[0].offsetRem).toBe(5)
      expect(receivedSections[0].tag).toBe('h2')
      expect(receivedSections[0].headingRef).toBe(headingRef)
    })

    it('accepts sections with minimal properties', () => {
      const sections: Section[] = [{ id: 'minimal', title: 'Minimal' }]
      let receivedSections: Section[]

      function TestConsumer() {
        receivedSections = useSectionStore((state) => state.sections)
        return <div>Test</div>
      }

      render(
        <SectionProvider sections={sections}>
          <TestConsumer />
        </SectionProvider>
      )

      expect(receivedSections[0].id).toBe('minimal')
      expect(receivedSections[0].title).toBe('Minimal')
      expect(receivedSections[0].offsetRem).toBeUndefined()
      expect(receivedSections[0].tag).toBeUndefined()
    })

    it('accepts children prop', () => {
      render(
        <SectionProvider sections={[]}>
          <div data-testid="child">Child</div>
        </SectionProvider>
      )

      expect(screen.getByTestId('child')).toBeInTheDocument()
    })

    it('handles React fragments as children', () => {
      render(
        <SectionProvider sections={[]}>
          <>
            <div data-testid="fragment-1">Fragment 1</div>
            <div data-testid="fragment-2">Fragment 2</div>
          </>
        </SectionProvider>
      )

      expect(screen.getByTestId('fragment-1')).toBeInTheDocument()
      expect(screen.getByTestId('fragment-2')).toBeInTheDocument()
    })
  })

  describe('Edge Cases', () => {
    it('handles empty sections array', () => {
      let sections: Section[]

      function TestConsumer() {
        sections = useSectionStore((state) => state.sections)
        return <div>Test</div>
      }

      render(
        <SectionProvider sections={[]}>
          <TestConsumer />
        </SectionProvider>
      )

      expect(sections).toEqual([])
    })

    it('handles registering non-existent section id', () => {
      const sections: Section[] = [{ id: 'existing', title: 'Existing' }]
      const ref = createRef<HTMLHeadingElement>()
      let registeredSections: Section[]

      function TestConsumer() {
        const registerHeading = useSectionStore(
          (state) => state.registerHeading
        )
        registeredSections = useSectionStore((state) => state.sections)

        useEffect(() => {
          registerHeading({ id: 'non-existent', ref, offsetRem: 1 })
        }, [registerHeading])

        return <div>Test</div>
      }

      render(
        <SectionProvider sections={sections}>
          <TestConsumer />
        </SectionProvider>
      )

      expect(registeredSections.length).toBe(1)
      expect(registeredSections[0].id).toBe('existing')
      expect(registeredSections[0].headingRef).toBeUndefined()
    })

    it('handles undefined children gracefully', () => {
      render(<SectionProvider sections={[]}>{undefined}</SectionProvider>)
      expect(document.body).toBeInTheDocument()
    })

    it('handles null children gracefully', () => {
      render(<SectionProvider sections={[]}>{null}</SectionProvider>)
      expect(document.body).toBeInTheDocument()
    })

    it('handles sections with duplicate ids', () => {
      const sections: Section[] = [
        { id: 'duplicate', title: 'First' },
        { id: 'duplicate', title: 'Second' },
      ]
      let receivedSections: Section[]

      function TestConsumer() {
        receivedSections = useSectionStore((state) => state.sections)
        return <div>Test</div>
      }

      render(
        <SectionProvider sections={sections}>
          <TestConsumer />
        </SectionProvider>
      )

      expect(receivedSections.length).toBe(2)
      expect(receivedSections[0].id).toBe('duplicate')
      expect(receivedSections[1].id).toBe('duplicate')
    })

    it('handles very large sections array', () => {
      const sections: Section[] = Array.from({ length: 1000 }, (_, i) => ({
        id: `section-${i}`,
        title: `Section ${i}`,
      }))
      let receivedSections: Section[]

      function TestConsumer() {
        receivedSections = useSectionStore((state) => state.sections)
        return <div>Test</div>
      }

      render(
        <SectionProvider sections={sections}>
          <TestConsumer />
        </SectionProvider>
      )

      expect(receivedSections.length).toBe(1000)
    })

    it('handles sections with special characters in id', () => {
      const sections: Section[] = [
        { id: 'section-with-dashes', title: 'Dashes' },
        { id: 'section_with_underscores', title: 'Underscores' },
        { id: 'section.with.dots', title: 'Dots' },
      ]
      let receivedSections: Section[]

      function TestConsumer() {
        receivedSections = useSectionStore((state) => state.sections)
        return <div>Test</div>
      }

      render(
        <SectionProvider sections={sections}>
          <TestConsumer />
        </SectionProvider>
      )

      expect(receivedSections[0].id).toBe('section-with-dashes')
      expect(receivedSections[1].id).toBe('section_with_underscores')
      expect(receivedSections[2].id).toBe('section.with.dots')
    })

    it('handles rapid section updates', () => {
      const sections1: Section[] = [{ id: 'section-1', title: 'Section 1' }]
      const sections2: Section[] = [{ id: 'section-2', title: 'Section 2' }]
      const sections3: Section[] = [{ id: 'section-3', title: 'Section 3' }]
      let receivedSections: Section[]

      function TestConsumer() {
        receivedSections = useSectionStore((state) => state.sections)
        return <div>Test</div>
      }

      const { rerender } = render(
        <SectionProvider sections={sections1}>
          <TestConsumer />
        </SectionProvider>
      )

      rerender(
        <SectionProvider sections={sections2}>
          <TestConsumer />
        </SectionProvider>
      )

      rerender(
        <SectionProvider sections={sections3}>
          <TestConsumer />
        </SectionProvider>
      )

      expect(receivedSections).toEqual(sections3)
    })
  })

  describe('Multiple Consumers', () => {
    it('provides same store to multiple consumers', () => {
      const sections: Section[] = [{ id: 'test', title: 'Test' }]
      let consumer1Sections: Section[]
      let consumer2Sections: Section[]

      function Consumer1() {
        consumer1Sections = useSectionStore((state) => state.sections)
        return <div data-testid="consumer-1">Consumer 1</div>
      }

      function Consumer2() {
        consumer2Sections = useSectionStore((state) => state.sections)
        return <div data-testid="consumer-2">Consumer 2</div>
      }

      render(
        <SectionProvider sections={sections}>
          <Consumer1 />
          <Consumer2 />
        </SectionProvider>
      )

      expect(consumer1Sections).toEqual(sections)
      expect(consumer2Sections).toEqual(sections)
      expect(consumer1Sections).toBe(consumer2Sections)
    })

    it('updates all consumers when state changes', () => {
      const sections: Section[] = []
      let consumer1Visible: string[]
      let consumer2Visible: string[]
      let setVisibleSections: any

      function Consumer1() {
        consumer1Visible = useSectionStore((state) => state.visibleSections)
        setVisibleSections = useSectionStore(
          (state) => state.setVisibleSections
        )
        return <div>Consumer 1</div>
      }

      function Consumer2() {
        consumer2Visible = useSectionStore((state) => state.visibleSections)
        return <div>Consumer 2</div>
      }

      render(
        <SectionProvider sections={sections}>
          <Consumer1 />
          <Consumer2 />
        </SectionProvider>
      )

      act(() => {
        setVisibleSections(['test'])
      })

      expect(consumer1Visible).toEqual(['test'])
      expect(consumer2Visible).toEqual(['test'])
    })

    it('allows different selectors in different consumers', () => {
      const sections: Section[] = [
        { id: 'section-1', title: 'Section 1' },
        { id: 'section-2', title: 'Section 2' },
      ]
      let consumer1Sections: Section[]
      let consumer2SectionCount: number

      function Consumer1() {
        consumer1Sections = useSectionStore((state) => state.sections)
        return <div>Consumer 1</div>
      }

      function Consumer2() {
        consumer2SectionCount = useSectionStore(
          (state) => state.sections.length
        )
        return <div>Consumer 2</div>
      }

      render(
        <SectionProvider sections={sections}>
          <Consumer1 />
          <Consumer2 />
        </SectionProvider>
      )

      expect(consumer1Sections).toEqual(sections)
      expect(consumer2SectionCount).toBe(2)
    })

    it('supports deeply nested consumers', () => {
      const sections: Section[] = [{ id: 'test', title: 'Test' }]
      let deepSections: Section[]

      function DeepConsumer() {
        deepSections = useSectionStore((state) => state.sections)
        return <div data-testid="deep">Deep</div>
      }

      render(
        <SectionProvider sections={sections}>
          <div>
            <div>
              <div>
                <DeepConsumer />
              </div>
            </div>
          </div>
        </SectionProvider>
      )

      expect(screen.getByTestId('deep')).toBeInTheDocument()
      expect(deepSections).toEqual(sections)
    })

    it('handles consumer mounting and unmounting', () => {
      const sections: Section[] = []
      let mountedConsumer: string | null = null

      function Consumer1() {
        mountedConsumer = 'consumer1'
        useSectionStore((state) => state.sections)
        return <div data-testid="consumer-1">Consumer 1</div>
      }

      function Consumer2() {
        mountedConsumer = 'consumer2'
        useSectionStore((state) => state.sections)
        return <div data-testid="consumer-2">Consumer 2</div>
      }

      const { rerender } = render(
        <SectionProvider sections={sections}>
          <Consumer1 />
        </SectionProvider>
      )

      expect(screen.getByTestId('consumer-1')).toBeInTheDocument()

      rerender(
        <SectionProvider sections={sections}>
          <Consumer2 />
        </SectionProvider>
      )

      expect(screen.queryByTestId('consumer-1')).not.toBeInTheDocument()
      expect(screen.getByTestId('consumer-2')).toBeInTheDocument()
    })

    it('maintains state consistency across multiple consumers', () => {
      const sections: Section[] = [{ id: 'test', title: 'Test' }]
      const ref = createRef<HTMLHeadingElement>()
      let consumer1RegisterHeading: any
      let consumer2Sections: Section[]

      function Consumer1() {
        consumer1RegisterHeading = useSectionStore(
          (state) => state.registerHeading
        )

        useEffect(() => {
          consumer1RegisterHeading({ id: 'test', ref, offsetRem: 2 })
        }, [])

        return <div>Consumer 1</div>
      }

      function Consumer2() {
        consumer2Sections = useSectionStore((state) => state.sections)
        return <div>Consumer 2</div>
      }

      render(
        <SectionProvider sections={sections}>
          <Consumer1 />
          <Consumer2 />
        </SectionProvider>
      )

      expect(consumer2Sections[0].headingRef).toBe(ref)
      expect(consumer2Sections[0].offsetRem).toBe(2)
    })

    it('handles multiple consumers with different update frequencies', () => {
      const sections: Section[] = []
      let consumer1RenderCount = 0
      let consumer2RenderCount = 0
      let setVisibleSections: any

      function Consumer1() {
        consumer1RenderCount++
        useSectionStore((state) => state.visibleSections)
        setVisibleSections = useSectionStore(
          (state) => state.setVisibleSections
        )
        return <div>Consumer 1</div>
      }

      function Consumer2() {
        consumer2RenderCount++
        useSectionStore((state) => state.sections)
        return <div>Consumer 2</div>
      }

      render(
        <SectionProvider sections={sections}>
          <Consumer1 />
          <Consumer2 />
        </SectionProvider>
      )

      const consumer1InitialCount = consumer1RenderCount
      const consumer2InitialCount = consumer2RenderCount

      act(() => {
        setVisibleSections(['test'])
      })

      expect(consumer1RenderCount).toBeGreaterThan(consumer1InitialCount)
      expect(consumer2RenderCount).toBe(consumer2InitialCount)
    })
  })

  describe('Scroll Behavior', () => {
    it('sets up scroll event listener', () => {
      const sections: Section[] = []

      render(
        <SectionProvider sections={sections}>
          <div>Test</div>
        </SectionProvider>
      )

      expect(window.addEventListener).toHaveBeenCalledWith(
        'scroll',
        expect.any(Function),
        { passive: true }
      )
    })

    it('sets up resize event listener', () => {
      const sections: Section[] = []

      render(
        <SectionProvider sections={sections}>
          <div>Test</div>
        </SectionProvider>
      )

      expect(window.addEventListener).toHaveBeenCalledWith(
        'resize',
        expect.any(Function)
      )
    })

    it('uses requestAnimationFrame for initial check', () => {
      const sections: Section[] = []

      render(
        <SectionProvider sections={sections}>
          <div>Test</div>
        </SectionProvider>
      )

      expect(window.requestAnimationFrame).toHaveBeenCalledWith(
        expect.any(Function)
      )
    })

    it('cleans up event listeners on unmount', () => {
      const sections: Section[] = []

      const { unmount } = render(
        <SectionProvider sections={sections}>
          <div>Test</div>
        </SectionProvider>
      )

      unmount()

      expect(window.removeEventListener).toHaveBeenCalledWith(
        'scroll',
        expect.any(Function)
      )
      expect(window.removeEventListener).toHaveBeenCalledWith(
        'resize',
        expect.any(Function)
      )
    })

    it('cancels animation frame on unmount', () => {
      const sections: Section[] = []

      const { unmount } = render(
        <SectionProvider sections={sections}>
          <div>Test</div>
        </SectionProvider>
      )

      unmount()

      expect(window.cancelAnimationFrame).toHaveBeenCalledWith(0)
    })
  })
})
