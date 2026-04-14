import { fireEvent, render, screen } from '@testing-library/react'
import React from 'react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../tabs'

describe('Tabs', () => {
  const TestTabs = ({
    value,
    defaultValue = 'tab1',
    onValueChange,
  }: {
    value?: string
    defaultValue?: string
    onValueChange?: (value: string) => void
  }) => (
    <Tabs
      value={value}
      defaultValue={defaultValue}
      onValueChange={onValueChange}
    >
      <TabsList>
        <TabsTrigger value="tab1">Tab 1</TabsTrigger>
        <TabsTrigger value="tab2">Tab 2</TabsTrigger>
        <TabsTrigger value="tab3">Tab 3</TabsTrigger>
      </TabsList>
      <TabsContent value="tab1">Content 1</TabsContent>
      <TabsContent value="tab2">Content 2</TabsContent>
      <TabsContent value="tab3">Content 3</TabsContent>
    </Tabs>
  )

  it('renders tabs with default value', () => {
    render(<TestTabs />)

    expect(screen.getByText('Tab 1')).toBeInTheDocument()
    expect(screen.getByText('Tab 2')).toBeInTheDocument()
    expect(screen.getByText('Tab 3')).toBeInTheDocument()
    expect(screen.getByText('Content 1')).toBeInTheDocument()
    expect(screen.queryByText('Content 2')).not.toBeInTheDocument()
    expect(screen.queryByText('Content 3')).not.toBeInTheDocument()
  })

  it('switches tabs when clicking triggers', () => {
    render(<TestTabs />)

    expect(screen.getByText('Content 1')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Tab 2'))
    expect(screen.queryByText('Content 1')).not.toBeInTheDocument()
    expect(screen.getByText('Content 2')).toBeInTheDocument()
    expect(screen.queryByText('Content 3')).not.toBeInTheDocument()

    fireEvent.click(screen.getByText('Tab 3'))
    expect(screen.queryByText('Content 1')).not.toBeInTheDocument()
    expect(screen.queryByText('Content 2')).not.toBeInTheDocument()
    expect(screen.getByText('Content 3')).toBeInTheDocument()
  })

  it('works as controlled component', () => {
    const { rerender } = render(<TestTabs value="tab1" />)

    expect(screen.getByText('Content 1')).toBeInTheDocument()
    expect(screen.queryByText('Content 2')).not.toBeInTheDocument()

    rerender(<TestTabs value="tab2" />)
    expect(screen.queryByText('Content 1')).not.toBeInTheDocument()
    expect(screen.getByText('Content 2')).toBeInTheDocument()
  })

  it('calls onValueChange when tab is clicked', () => {
    const handleChange = jest.fn()
    render(<TestTabs onValueChange={handleChange} />)

    fireEvent.click(screen.getByText('Tab 2'))
    expect(handleChange).toHaveBeenCalledWith('tab2')

    fireEvent.click(screen.getByText('Tab 3'))
    expect(handleChange).toHaveBeenCalledWith('tab3')
  })

  it('applies active styles to selected tab', () => {
    render(<TestTabs />)

    const tab1 = screen.getByText('Tab 1')
    const tab2 = screen.getByText('Tab 2')

    expect(tab1).toHaveClass('bg-white')
    expect(tab1).toHaveClass('text-zinc-900')
    expect(tab1).toHaveClass('shadow-sm')

    expect(tab2).not.toHaveClass('bg-white')
    expect(tab2).toHaveClass('text-zinc-600')
  })

  it('updates active styles when switching tabs', () => {
    render(<TestTabs />)

    const tab1 = screen.getByText('Tab 1')
    const tab2 = screen.getByText('Tab 2')

    expect(tab1).toHaveClass('bg-white')
    expect(tab2).not.toHaveClass('bg-white')

    fireEvent.click(tab2)

    expect(tab1).not.toHaveClass('bg-white')
    expect(tab2).toHaveClass('bg-white')
  })

  it('applies custom className to Tabs', () => {
    render(
      <Tabs defaultValue="tab1" className="custom-tabs">
        <TabsList>
          <TabsTrigger value="tab1">Tab 1</TabsTrigger>
        </TabsList>
        <TabsContent value="tab1">Content</TabsContent>
      </Tabs>
    )

    const container = screen.getByText('Tab 1').closest('.custom-tabs')
    expect(container).toBeInTheDocument()
  })

  it('applies custom className to TabsList', () => {
    render(
      <Tabs defaultValue="tab1">
        <TabsList className="custom-list">
          <TabsTrigger value="tab1">Tab 1</TabsTrigger>
        </TabsList>
        <TabsContent value="tab1">Content</TabsContent>
      </Tabs>
    )

    const list = screen.getByText('Tab 1').parentElement
    expect(list).toHaveClass('custom-list')
    expect(list).toHaveClass('inline-flex')
  })

  it('applies custom className to TabsTrigger', () => {
    render(
      <Tabs defaultValue="tab1">
        <TabsList>
          <TabsTrigger value="tab1" className="custom-trigger">
            Tab 1
          </TabsTrigger>
        </TabsList>
        <TabsContent value="tab1">Content</TabsContent>
      </Tabs>
    )

    const trigger = screen.getByText('Tab 1')
    expect(trigger).toHaveClass('custom-trigger')
  })

  it('applies custom className to TabsContent', () => {
    render(
      <Tabs defaultValue="tab1">
        <TabsList>
          <TabsTrigger value="tab1">Tab 1</TabsTrigger>
        </TabsList>
        <TabsContent value="tab1" className="custom-content">
          Content
        </TabsContent>
      </Tabs>
    )

    const content = screen.getByText('Content')
    expect(content).toBeInTheDocument()
    // The content div should have the custom class
    const contentDiv = content.closest('.custom-content')
    expect(contentDiv).toBeInTheDocument()
  })

  it('throws error when TabsTrigger is used outside Tabs', () => {
    const spy = jest.spyOn(console, 'error').mockImplementation(() => {})

    expect(() => {
      render(<TabsTrigger value="tab1">Tab 1</TabsTrigger>)
    }).toThrow('TabsTrigger must be used within Tabs')

    spy.mockRestore()
  })

  it('throws error when TabsContent is used outside Tabs', () => {
    const spy = jest.spyOn(console, 'error').mockImplementation(() => {})

    expect(() => {
      render(<TabsContent value="tab1">Content</TabsContent>)
    }).toThrow('TabsContent must be used within Tabs')

    spy.mockRestore()
  })

  it('handles empty default value', () => {
    render(
      <Tabs defaultValue="">
        <TabsList>
          <TabsTrigger value="tab1">Tab 1</TabsTrigger>
          <TabsTrigger value="tab2">Tab 2</TabsTrigger>
        </TabsList>
        <TabsContent value="tab1">Content 1</TabsContent>
        <TabsContent value="tab2">Content 2</TabsContent>
      </Tabs>
    )

    // No content should be visible with empty default value
    expect(screen.queryByText('Content 1')).not.toBeInTheDocument()
    expect(screen.queryByText('Content 2')).not.toBeInTheDocument()

    // But tabs should still be clickable
    fireEvent.click(screen.getByText('Tab 1'))
    expect(screen.getByText('Content 1')).toBeInTheDocument()
  })

  it('handles different default values', () => {
    render(<TestTabs defaultValue="tab2" />)

    expect(screen.queryByText('Content 1')).not.toBeInTheDocument()
    expect(screen.getByText('Content 2')).toBeInTheDocument()
    expect(screen.queryByText('Content 3')).not.toBeInTheDocument()
  })

  it('maintains state across multiple switches', () => {
    render(<TestTabs />)

    expect(screen.getByText('Content 1')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Tab 2'))
    expect(screen.getByText('Content 2')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Tab 3'))
    expect(screen.getByText('Content 3')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Tab 1'))
    expect(screen.getByText('Content 1')).toBeInTheDocument()
  })

  it('works with both controlled and uncontrolled modes', () => {
    const ControlledTest = () => {
      const [value, setValue] = React.useState('tab1')

      return (
        <>
          <button onClick={() => setValue('tab2')}>Set Tab 2</button>
          <Tabs value={value} onValueChange={setValue}>
            <TabsList>
              <TabsTrigger value="tab1">Tab 1</TabsTrigger>
              <TabsTrigger value="tab2">Tab 2</TabsTrigger>
            </TabsList>
            <TabsContent value="tab1">Content 1</TabsContent>
            <TabsContent value="tab2">Content 2</TabsContent>
          </Tabs>
        </>
      )
    }

    render(<ControlledTest />)

    expect(screen.getByText('Content 1')).toBeInTheDocument()

    // External control
    fireEvent.click(screen.getByText('Set Tab 2'))
    expect(screen.getByText('Content 2')).toBeInTheDocument()

    // Internal control via tab click
    fireEvent.click(screen.getByText('Tab 1'))
    expect(screen.getByText('Content 1')).toBeInTheDocument()
  })
})
