import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../Tabs'

describe('Tabs', () => {
  const TestTabs = ({ defaultValue = 'tab1' }: { defaultValue?: string }) => (
    <Tabs defaultValue={defaultValue}>
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

  it('renders tabs with default active tab', async () => {
    render(<TestTabs />)

    expect(screen.getByText('Tab 1')).toBeInTheDocument()
    expect(screen.getByText('Tab 2')).toBeInTheDocument()
    expect(screen.getByText('Tab 3')).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText('Content 1')).toBeInTheDocument()
    })

    expect(screen.queryByText('Content 2')).not.toBeInTheDocument()
    expect(screen.queryByText('Content 3')).not.toBeInTheDocument()
  })

  it('switches tabs when clicking triggers', async () => {
    render(<TestTabs />)

    await waitFor(() => {
      expect(screen.getByText('Content 1')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Tab 2'))

    await waitFor(() => {
      expect(screen.queryByText('Content 1')).not.toBeInTheDocument()
      expect(screen.getByText('Content 2')).toBeInTheDocument()
      expect(screen.queryByText('Content 3')).not.toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Tab 3'))

    await waitFor(() => {
      expect(screen.queryByText('Content 1')).not.toBeInTheDocument()
      expect(screen.queryByText('Content 2')).not.toBeInTheDocument()
      expect(screen.getByText('Content 3')).toBeInTheDocument()
    })
  })

  it('applies active styles to active tab trigger', async () => {
    render(<TestTabs />)

    await waitFor(() => {
      const tab1Button = screen.getByText('Tab 1')
      expect(tab1Button).toHaveClass('bg-white')
      expect(tab1Button).toHaveClass('shadow-sm')
    })

    const tab2Button = screen.getByText('Tab 2')
    expect(tab2Button).not.toHaveClass('bg-white')
    expect(tab2Button).not.toHaveClass('shadow-sm')
  })

  it('changes active styles when switching tabs', async () => {
    render(<TestTabs />)

    await waitFor(() => {
      expect(screen.getByText('Tab 1')).toHaveClass('bg-white')
    })

    fireEvent.click(screen.getByText('Tab 2'))

    await waitFor(() => {
      expect(screen.getByText('Tab 1')).not.toHaveClass('bg-white')
      expect(screen.getByText('Tab 2')).toHaveClass('bg-white')
    })
  })

  it('renders with custom className on Tabs', () => {
    render(
      <Tabs defaultValue="tab1" className="custom-tabs">
        <TabsList>
          <TabsTrigger value="tab1">Tab 1</TabsTrigger>
        </TabsList>
        <TabsContent value="tab1">Content 1</TabsContent>
      </Tabs>,
    )

    const tabsContainer = screen.getByText('Tab 1').closest('.custom-tabs')
    expect(tabsContainer).toBeInTheDocument()
  })

  it('renders with custom className on TabsList', () => {
    render(
      <Tabs defaultValue="tab1">
        <TabsList className="custom-list">
          <TabsTrigger value="tab1">Tab 1</TabsTrigger>
        </TabsList>
        <TabsContent value="tab1">Content 1</TabsContent>
      </Tabs>,
    )

    const listContainer = screen.getByText('Tab 1').parentElement
    expect(listContainer).toHaveClass('custom-list')
  })

  it('renders with custom className on TabsTrigger', () => {
    render(
      <Tabs defaultValue="tab1">
        <TabsList>
          <TabsTrigger value="tab1" className="custom-trigger">
            Tab 1
          </TabsTrigger>
        </TabsList>
        <TabsContent value="tab1">Content 1</TabsContent>
      </Tabs>,
    )

    const trigger = screen.getByText('Tab 1')
    expect(trigger).toHaveClass('custom-trigger')
  })

  it('renders with custom className on TabsContent', async () => {
    render(
      <Tabs defaultValue="tab1">
        <TabsList>
          <TabsTrigger value="tab1">Tab 1</TabsTrigger>
        </TabsList>
        <TabsContent value="tab1" className="custom-content">
          Content 1
        </TabsContent>
      </Tabs>,
    )

    await waitFor(() => {
      const content = screen.getByText('Content 1')
      const contentContainer = content.closest('.custom-content')
      expect(contentContainer).toBeInTheDocument()
    })
  })

  it('handles forceMount prop on TabsContent', async () => {
    render(
      <Tabs defaultValue="tab1">
        <TabsList>
          <TabsTrigger value="tab1">Tab 1</TabsTrigger>
          <TabsTrigger value="tab2">Tab 2</TabsTrigger>
        </TabsList>
        <TabsContent value="tab1">Content 1</TabsContent>
        <TabsContent value="tab2" forceMount>
          Content 2
        </TabsContent>
      </Tabs>,
    )

    // Wait for initial mount
    await waitFor(() => {
      // Content 2 should be in DOM but hidden
      const content2 = screen.getByText('Content 2')
      expect(content2).toBeInTheDocument()
      const content2Container = content2.closest('[style*="display"]')
      expect(content2Container).toHaveStyle({ display: 'none' })
    })
  })

  it('shows force mounted content when active', async () => {
    render(
      <Tabs defaultValue="tab1">
        <TabsList>
          <TabsTrigger value="tab1">Tab 1</TabsTrigger>
          <TabsTrigger value="tab2">Tab 2</TabsTrigger>
        </TabsList>
        <TabsContent value="tab1" forceMount>
          Content 1
        </TabsContent>
        <TabsContent value="tab2" forceMount>
          Content 2
        </TabsContent>
      </Tabs>,
    )

    await waitFor(() => {
      const content1 = screen.getByText('Content 1')
      const content1Container = content1.closest('[style]')
      expect(content1Container).toHaveStyle({ display: 'block' })

      const content2 = screen.getByText('Content 2')
      const content2Container = content2.closest('[style]')
      expect(content2Container).toHaveStyle({ display: 'none' })
    })

    fireEvent.click(screen.getByText('Tab 2'))

    await waitFor(() => {
      const content1 = screen.getByText('Content 1')
      const content1Container = content1.closest('[style]')
      expect(content1Container).toHaveStyle({ display: 'none' })

      const content2 = screen.getByText('Content 2')
      const content2Container = content2.closest('[style]')
      expect(content2Container).toHaveStyle({ display: 'block' })
    })
  })

  it('renders disabled button when TabsTrigger is used outside Tabs', () => {
    // No longer throws error, renders a disabled button instead
    render(<TabsTrigger value="tab1">Tab 1</TabsTrigger>)

    const button = screen.getByText('Tab 1')
    expect(button).toBeInTheDocument()
    expect(button).toBeDisabled()
  })

  it('returns null when TabsContent is used outside Tabs', () => {
    // No longer throws error, returns null instead
    const { container } = render(
      <TabsContent value="tab1">Content 1</TabsContent>,
    )

    expect(container.firstChild).toBeNull()
    expect(screen.queryByText('Content 1')).not.toBeInTheDocument()
  })

  it('handles different default values', async () => {
    render(<TestTabs defaultValue="tab2" />)

    await waitFor(() => {
      expect(screen.queryByText('Content 1')).not.toBeInTheDocument()
      expect(screen.getByText('Content 2')).toBeInTheDocument()
      expect(screen.queryByText('Content 3')).not.toBeInTheDocument()
    })
  })

  it('maintains tab state across multiple switches', async () => {
    render(<TestTabs />)

    await waitFor(() => {
      expect(screen.getByText('Content 1')).toBeInTheDocument()
    })

    // Switch to tab 2
    fireEvent.click(screen.getByText('Tab 2'))
    await waitFor(() => {
      expect(screen.getByText('Content 2')).toBeInTheDocument()
    })

    // Switch to tab 3
    fireEvent.click(screen.getByText('Tab 3'))
    await waitFor(() => {
      expect(screen.getByText('Content 3')).toBeInTheDocument()
    })

    // Switch back to tab 1
    fireEvent.click(screen.getByText('Tab 1'))
    await waitFor(() => {
      expect(screen.getByText('Content 1')).toBeInTheDocument()
    })
  })
})

describe('Tabs — defaultValue re-sync guard', () => {
  const GuardTabs = ({ defaultValue }: { defaultValue: string }) => (
    <Tabs defaultValue={defaultValue}>
      <TabsList>
        <TabsTrigger value="tab1">Tab 1</TabsTrigger>
        <TabsTrigger value="tab2">Tab 2</TabsTrigger>
      </TabsList>
      <TabsContent value="tab1">Content 1</TabsContent>
      <TabsContent value="tab2">Content 2</TabsContent>
    </Tabs>
  )

  it('follows a changed defaultValue while the user has not clicked', async () => {
    const { rerender } = render(<GuardTabs defaultValue="tab1" />)
    await waitFor(() => {
      expect(screen.getByText('Content 1')).toBeInTheDocument()
    })

    rerender(<GuardTabs defaultValue="tab2" />)
    await waitFor(() => {
      expect(screen.getByText('Content 2')).toBeInTheDocument()
    })
  })

  it('does not yank the user off their chosen tab when defaultValue changes', async () => {
    const { rerender } = render(<GuardTabs defaultValue="tab1" />)
    await waitFor(() => {
      expect(screen.getByText('Content 1')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Tab 2'))
    await waitFor(() => {
      expect(screen.getByText('Content 2')).toBeInTheDocument()
    })

    // A recomputed default must not override the explicit user choice.
    rerender(<GuardTabs defaultValue="tab1" />)
    expect(screen.getByText('Content 2')).toBeInTheDocument()
    expect(screen.queryByText('Content 1')).not.toBeInTheDocument()
  })
})

describe('Tabs — controlled mode', () => {
  const Controlled = ({
    value,
    onValueChange,
  }: {
    value: string
    onValueChange?: (v: string) => void
  }) => (
    <Tabs defaultValue="tab1" value={value} onValueChange={onValueChange}>
      <TabsList>
        <TabsTrigger value="tab1">Tab 1</TabsTrigger>
        <TabsTrigger value="tab2">Tab 2</TabsTrigger>
      </TabsList>
      <TabsContent value="tab1">Content 1</TabsContent>
      <TabsContent value="tab2">Content 2</TabsContent>
    </Tabs>
  )

  it('renders the tab named by value and follows value changes', async () => {
    const { rerender } = render(<Controlled value="tab2" />)
    await waitFor(() => {
      expect(screen.getByText('Content 2')).toBeInTheDocument()
    })

    rerender(<Controlled value="tab1" />)
    expect(screen.getByText('Content 1')).toBeInTheDocument()
    expect(screen.queryByText('Content 2')).not.toBeInTheDocument()
  })

  it('reports clicks via onValueChange without switching on its own', async () => {
    const onValueChange = jest.fn()
    render(<Controlled value="tab1" onValueChange={onValueChange} />)
    await waitFor(() => {
      expect(screen.getByText('Content 1')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Tab 2'))
    expect(onValueChange).toHaveBeenCalledWith('tab2')
    // Still controlled by the unchanged value prop.
    expect(screen.getByText('Content 1')).toBeInTheDocument()
    expect(screen.queryByText('Content 2')).not.toBeInTheDocument()
  })

  it('spreads extra div props such as data-testid', () => {
    render(
      <Tabs defaultValue="tab1" data-testid="my-tabs">
        <TabsContent value="tab1">Content 1</TabsContent>
      </Tabs>,
    )
    expect(screen.getByTestId('my-tabs')).toBeInTheDocument()
  })
})

describe('Tabs — ARIA tabs pattern', () => {
  const AriaTabs = ({
    onValueChange,
  }: {
    onValueChange?: (v: string) => void
  }) => (
    <Tabs defaultValue="one" onValueChange={onValueChange}>
      <TabsList aria-label="Methods">
        <TabsTrigger value="one">One</TabsTrigger>
        <TabsTrigger value="two words">Two</TabsTrigger>
        <TabsTrigger value="off" disabled>
          Off
        </TabsTrigger>
        <TabsTrigger value="four">Four</TabsTrigger>
      </TabsList>
      <TabsContent value="one">Panel one</TabsContent>
      <TabsContent value="two words">Panel two</TabsContent>
      <TabsContent value="four">Panel four</TabsContent>
    </Tabs>
  )

  it('exposes a named tablist with selectable tabs', async () => {
    render(<AriaTabs />)
    const list = screen.getByRole('tablist', { name: 'Methods' })
    expect(list).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: 'One' })).toHaveAttribute(
        'aria-selected',
        'true',
      )
    })
    expect(screen.getByRole('tab', { name: 'Two' })).toHaveAttribute(
      'aria-selected',
      'false',
    )

    fireEvent.click(screen.getByRole('tab', { name: 'Two' }))
    expect(screen.getByRole('tab', { name: 'Two' })).toHaveAttribute(
      'aria-selected',
      'true',
    )
    expect(screen.getByRole('tab', { name: 'One' })).toHaveAttribute(
      'aria-selected',
      'false',
    )
  })

  it('labels each panel by its tab, also for values with spaces', async () => {
    render(<AriaTabs />)
    fireEvent.click(screen.getByRole('tab', { name: 'Two' }))
    const panel = await screen.findByRole('tabpanel', { name: 'Two' })
    expect(panel).toHaveTextContent('Panel two')
    const tab = screen.getByRole('tab', { name: 'Two' })
    expect(tab.id).toMatch(/^[^\s]+$/)
    expect(panel).toHaveAttribute('aria-labelledby', tab.id)
  })

  it('moves and selects with the arrow keys, Home and End, skipping disabled tabs', async () => {
    const onValueChange = jest.fn()
    render(<AriaTabs onValueChange={onValueChange} />)
    const one = screen.getByRole('tab', { name: 'One' })
    one.focus()

    fireEvent.keyDown(one, { key: 'ArrowRight' })
    const two = screen.getByRole('tab', { name: 'Two' })
    expect(two).toHaveFocus()
    expect(onValueChange).toHaveBeenLastCalledWith('two words')

    fireEvent.keyDown(two, { key: 'ArrowRight' })
    const four = screen.getByRole('tab', { name: 'Four' })
    expect(four).toHaveFocus()
    expect(onValueChange).toHaveBeenLastCalledWith('four')

    // Wraps around at the end.
    fireEvent.keyDown(four, { key: 'ArrowRight' })
    expect(one).toHaveFocus()

    fireEvent.keyDown(one, { key: 'ArrowLeft' })
    expect(four).toHaveFocus()

    fireEvent.keyDown(four, { key: 'Home' })
    expect(one).toHaveFocus()

    fireEvent.keyDown(one, { key: 'End' })
    expect(four).toHaveFocus()
    expect(await screen.findByText('Panel four')).toBeInTheDocument()
  })

  it('leaves other keys and handled events alone', () => {
    const onValueChange = jest.fn()
    const onKeyDown = jest.fn((e: React.KeyboardEvent) => {
      if (e.key === 'ArrowLeft') e.preventDefault()
    })
    render(
      <Tabs defaultValue="a" onValueChange={onValueChange}>
        <TabsList onKeyDown={onKeyDown}>
          <TabsTrigger value="a">A</TabsTrigger>
          <TabsTrigger value="b">B</TabsTrigger>
        </TabsList>
      </Tabs>,
    )
    const a = screen.getByRole('tab', { name: 'A' })
    a.focus()
    fireEvent.keyDown(a, { key: 'Enter' })
    fireEvent.keyDown(a, { key: 'ArrowLeft' })
    expect(onKeyDown).toHaveBeenCalledTimes(2)
    expect(onValueChange).not.toHaveBeenCalled()
    expect(a).toHaveFocus()
  })

  it('renders the fallback trigger outside Tabs as an unselected tab', () => {
    render(<TabsTrigger value="x">Loose</TabsTrigger>)
    const tab = screen.getByRole('tab', { name: 'Loose' })
    expect(tab).toHaveAttribute('aria-selected', 'false')
    expect(tab).toBeDisabled()
  })
})
