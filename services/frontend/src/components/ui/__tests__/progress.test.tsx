/**
 * @jest-environment jsdom
 */

import { render, screen } from '@testing-library/react'
import { Progress } from '../progress'

describe('Progress', () => {
  it('renders progress container and bar', () => {
    const { container } = render(<Progress />)
    const progressContainer = container.firstChild as HTMLDivElement
    const progressBar = progressContainer.firstChild as HTMLDivElement

    expect(progressContainer).toBeTruthy()
    expect(progressContainer).toHaveClass(
      'relative',
      'h-4',
      'w-full',
      'overflow-hidden',
      'rounded-full'
    )
    expect(progressBar).toBeTruthy()
    expect(progressBar).toHaveClass(
      'h-full',
      'w-full',
      'flex-1',
      'transition-all'
    )
  })

  it('renders with custom value and max', () => {
    const { container } = render(<Progress value={50} max={100} />)
    const progressContainer = container.firstChild as HTMLDivElement
    const progressBar = progressContainer.firstChild as HTMLDivElement

    expect(progressContainer).toBeTruthy()
    expect(progressBar).toBeTruthy()
  })

  it('applies custom className', () => {
    render(<Progress className="custom-class" data-testid="progress" />)
    const progress = screen.getByTestId('progress')
    expect(progress).toHaveClass('custom-class')
    expect(progress).toHaveClass('relative', 'h-4', 'w-full')
  })

  it('accepts additional HTML attributes', () => {
    render(
      <Progress
        data-testid="progress"
        role="progressbar"
        aria-label="Loading"
      />
    )
    const progress = screen.getByTestId('progress')
    expect(progress).toHaveAttribute('role', 'progressbar')
    expect(progress).toHaveAttribute('aria-label', 'Loading')
  })

  it('renders with different values', () => {
    const values = [0, 25, 50, 75, 100, 150, -50]
    values.forEach((value) => {
      const { container } = render(<Progress value={value} />)
      const progressContainer = container.firstChild as HTMLDivElement
      expect(progressContainer).toBeTruthy()
    })
  })
})
