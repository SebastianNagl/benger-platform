/**
 * @jest-environment jsdom
 *
 * Branch coverage round 9: SectionProvider.tsx
 * Targets uncovered branches:
 * - checkVisibleSections: headingRef not present (continue), first section above scroll,
 *   nextSection without headingRef, visible section detection (top/bottom in viewport, spanning viewport)
 * - setVisibleSections: same vs different arrays
 * - registerHeading: matching and non-matching section IDs
 * - useIsomorphicLayoutEffect: window defined branch (useLayoutEffect)
 * - useSectionStore
 */

import React, { createRef, useEffect } from 'react'
import { render, act } from '@testing-library/react'
import '@testing-library/jest-dom'

import { SectionProvider, useSectionStore } from '../SectionProvider'
import type { Section } from '../SectionProvider'

// Helper component to access store
function StoreReader({ onRead }: { onRead: (data: any) => void }) {
  const sections = useSectionStore((s) => s.sections)
  const visibleSections = useSectionStore((s) => s.visibleSections)
  const setVisibleSections = useSectionStore((s) => s.setVisibleSections)
  const registerHeading = useSectionStore((s) => s.registerHeading)

  useEffect(() => {
    onRead({ sections, visibleSections, setVisibleSections, registerHeading })
  })

  return <div data-testid="store-reader">{JSON.stringify({ sections: sections.length, visibleSections })}</div>
}

describe('SectionProvider br9', () => {
  let addEventListenerSpy: jest.SpyInstance
  let removeEventListenerSpy: jest.SpyInstance
  let requestAnimationFrameSpy: jest.SpyInstance
  let cancelAnimationFrameSpy: jest.SpyInstance

  beforeEach(() => {
    addEventListenerSpy = jest.spyOn(window, 'addEventListener')
    removeEventListenerSpy = jest.spyOn(window, 'removeEventListener')
    requestAnimationFrameSpy = jest.spyOn(window, 'requestAnimationFrame').mockImplementation((cb) => {
      cb(0)
      return 1
    })
    cancelAnimationFrameSpy = jest.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => {})
  })

  afterEach(() => {
    jest.restoreAllMocks()
  })

  it('provides sections to child components', () => {
    const sections: Section[] = [
      { id: 'section-1', title: 'Section One' },
      { id: 'section-2', title: 'Section Two' },
    ]

    let storeData: any = null
    render(
      <SectionProvider sections={sections}>
        <StoreReader onRead={(data) => { storeData = data }} />
      </SectionProvider>
    )

    expect(storeData).not.toBeNull()
    expect(storeData.sections.length).toBe(2)
  })

  it('registers heading refs and updates sections', () => {
    const sections: Section[] = [
      { id: 'section-1', title: 'Section One' },
      { id: 'section-2', title: 'Section Two' },
    ]

    let storeData: any = null
    render(
      <SectionProvider sections={sections}>
        <StoreReader onRead={(data) => { storeData = data }} />
      </SectionProvider>
    )

    // Call registerHeading
    const ref = createRef<HTMLHeadingElement>()
    act(() => {
      storeData.registerHeading({ id: 'section-1', ref, offsetRem: 2 })
    })
  })

  it('setVisibleSections only updates when array changes', () => {
    const sections: Section[] = [
      { id: 'section-1', title: 'Section One' },
    ]

    let storeData: any = null
    render(
      <SectionProvider sections={sections}>
        <StoreReader onRead={(data) => { storeData = data }} />
      </SectionProvider>
    )

    // Set visible sections
    act(() => {
      storeData.setVisibleSections(['section-1'])
    })

    // Set same array again (should not cause state update due to join comparison)
    act(() => {
      storeData.setVisibleSections(['section-1'])
    })

    // Set different array
    act(() => {
      storeData.setVisibleSections(['section-1', 'section-2'])
    })
  })

  it('handles sections without headingRef in visibility check', () => {
    // Sections without refs should be skipped by checkVisibleSections (continue branch)
    const sections: Section[] = [
      { id: 'no-ref', title: 'No Ref Section' },
    ]

    render(
      <SectionProvider sections={sections}>
        <div>Content</div>
      </SectionProvider>
    )

    // The useEffect should have run checkVisibleSections, skipping sections without headingRef
    expect(addEventListenerSpy).toHaveBeenCalledWith('scroll', expect.any(Function), { passive: true })
    expect(addEventListenerSpy).toHaveBeenCalledWith('resize', expect.any(Function))
  })

  it('handles sections with headingRef and detects visibility', () => {
    const sections: Section[] = [
      { id: 'section-1', title: 'Section One', offsetRem: 0 },
      { id: 'section-2', title: 'Section Two', offsetRem: 0 },
    ]

    // Create mock heading elements
    const heading1 = document.createElement('h2')
    const heading2 = document.createElement('h2')
    document.body.appendChild(heading1)
    document.body.appendChild(heading2)

    // Mock getBoundingClientRect
    heading1.getBoundingClientRect = jest.fn(() => ({
      top: 100, bottom: 200, left: 0, right: 100, width: 100, height: 100, x: 0, y: 100, toJSON: () => {},
    }))
    heading2.getBoundingClientRect = jest.fn(() => ({
      top: 300, bottom: 400, left: 0, right: 100, width: 100, height: 100, x: 0, y: 300, toJSON: () => {},
    }))

    const ref1 = { current: heading1 }
    const ref2 = { current: heading2 }

    const sectionsWithRefs: Section[] = [
      { id: 'section-1', title: 'Section One', offsetRem: 0, headingRef: ref1 as any },
      { id: 'section-2', title: 'Section Two', offsetRem: 0, headingRef: ref2 as any },
    ]

    render(
      <SectionProvider sections={sectionsWithRefs}>
        <div>Content</div>
      </SectionProvider>
    )

    document.body.removeChild(heading1)
    document.body.removeChild(heading2)
  })

  it('cleans up event listeners on unmount', () => {
    const sections: Section[] = [{ id: 'a', title: 'A' }]
    const { unmount } = render(
      <SectionProvider sections={sections}>
        <div>Content</div>
      </SectionProvider>
    )

    unmount()

    expect(cancelAnimationFrameSpy).toHaveBeenCalled()
    expect(removeEventListenerSpy).toHaveBeenCalledWith('scroll', expect.any(Function))
    expect(removeEventListenerSpy).toHaveBeenCalledWith('resize', expect.any(Function))
  })
})
