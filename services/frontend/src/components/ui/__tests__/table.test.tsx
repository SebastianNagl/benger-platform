import { render, screen } from '@testing-library/react'
import React from 'react'
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from '../table'

describe('Table', () => {
  it('renders table with wrapper div', () => {
    const { container } = render(
      <Table>
        <TableBody>
          <TableRow>
            <TableCell>Test Cell</TableCell>
          </TableRow>
        </TableBody>
      </Table>
    )

    const wrapper = container.firstChild as HTMLElement
    expect(wrapper.tagName).toBe('DIV')
    expect(wrapper).toHaveClass('relative', 'w-full', 'overflow-auto')

    const table = wrapper.firstChild as HTMLElement
    expect(table.tagName).toBe('TABLE')
    expect(screen.getByText('Test Cell')).toBeInTheDocument()
  })

  it('applies custom className to table', () => {
    const { container } = render(
      <Table className="custom-table">
        <TableBody>
          <TableRow>
            <TableCell>Content</TableCell>
          </TableRow>
        </TableBody>
      </Table>
    )

    const table = container.querySelector('table')
    expect(table).toHaveClass('custom-table')
    expect(table).toHaveClass('w-full', 'caption-bottom', 'text-sm')
  })

  it('forwards ref to table element', () => {
    const ref = React.createRef<HTMLTableElement>()
    render(
      <Table ref={ref}>
        <TableBody>
          <TableRow>
            <TableCell>Content</TableCell>
          </TableRow>
        </TableBody>
      </Table>
    )

    expect(ref.current).toBeInstanceOf(HTMLTableElement)
  })
})

describe('TableHeader', () => {
  it('renders thead element', () => {
    const { container } = render(
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Header</TableHead>
          </TableRow>
        </TableHeader>
      </Table>
    )

    const thead = container.querySelector('thead')
    expect(thead).toBeInTheDocument()
    expect(screen.getByText('Header')).toBeInTheDocument()
  })

  it('applies border styling', () => {
    const { container } = render(
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Header</TableHead>
          </TableRow>
        </TableHeader>
      </Table>
    )

    const thead = container.querySelector('thead')
    expect(thead).toHaveClass('[&_tr]:border-b')
  })
})

describe('TableBody', () => {
  it('renders tbody element', () => {
    const { container } = render(
      <Table>
        <TableBody>
          <TableRow>
            <TableCell>Body Content</TableCell>
          </TableRow>
        </TableBody>
      </Table>
    )

    const tbody = container.querySelector('tbody')
    expect(tbody).toBeInTheDocument()
    expect(tbody).toHaveClass('[&_tr:last-child]:border-0')
    expect(screen.getByText('Body Content')).toBeInTheDocument()
  })
})

describe('TableFooter', () => {
  it('renders tfoot element with styling', () => {
    const { container } = render(
      <Table>
        <TableFooter>
          <TableRow>
            <TableCell>Footer Content</TableCell>
          </TableRow>
        </TableFooter>
      </Table>
    )

    const tfoot = container.querySelector('tfoot')
    expect(tfoot).toBeInTheDocument()
    expect(tfoot).toHaveClass('bg-zinc-50', 'font-medium')
    expect(screen.getByText('Footer Content')).toBeInTheDocument()
  })
})

describe('TableRow', () => {
  it('renders tr element with hover styles', () => {
    const { container } = render(
      <Table>
        <TableBody>
          <TableRow>
            <TableCell>Row Content</TableCell>
          </TableRow>
        </TableBody>
      </Table>
    )

    const tr = container.querySelector('tr')
    expect(tr).toBeInTheDocument()
    expect(tr).toHaveClass('border-b', 'transition-colors')
    expect(screen.getByText('Row Content')).toBeInTheDocument()
  })

  it('applies selected state styling', () => {
    const { container } = render(
      <Table>
        <TableBody>
          <TableRow data-state="selected">
            <TableCell>Selected Row</TableCell>
          </TableRow>
        </TableBody>
      </Table>
    )

    const tr = container.querySelector('tr')
    expect(tr).toHaveAttribute('data-state', 'selected')
    expect(tr).toHaveClass('data-[state=selected]:bg-zinc-100')
  })
})

describe('TableHead', () => {
  it('renders th element with styling', () => {
    const { container } = render(
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Column Header</TableHead>
          </TableRow>
        </TableHeader>
      </Table>
    )

    const th = container.querySelector('th')
    expect(th).toBeInTheDocument()
    expect(th).toHaveClass('h-12', 'px-4', 'text-left', 'font-medium')
    expect(screen.getByText('Column Header')).toBeInTheDocument()
  })

  it('applies custom className', () => {
    const { container } = render(
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="custom-header">Header</TableHead>
          </TableRow>
        </TableHeader>
      </Table>
    )

    const th = container.querySelector('th')
    expect(th).toHaveClass('custom-header')
  })
})

describe('TableCell', () => {
  it('renders td element with padding', () => {
    const { container } = render(
      <Table>
        <TableBody>
          <TableRow>
            <TableCell>Cell Content</TableCell>
          </TableRow>
        </TableBody>
      </Table>
    )

    const td = container.querySelector('td')
    expect(td).toBeInTheDocument()
    expect(td).toHaveClass('p-4', 'align-middle')
    expect(screen.getByText('Cell Content')).toBeInTheDocument()
  })

  it('handles checkbox role styling', () => {
    const { container } = render(
      <Table>
        <TableBody>
          <TableRow>
            <TableCell>
              <input type="checkbox" role="checkbox" />
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    )

    const td = container.querySelector('td')
    expect(td).toHaveClass('[&:has([role=checkbox])]:pr-0')
  })
})

describe('TableCaption', () => {
  it('renders caption element with styling', () => {
    const { container } = render(
      <Table>
        <TableCaption>Table Caption Text</TableCaption>
        <TableBody>
          <TableRow>
            <TableCell>Content</TableCell>
          </TableRow>
        </TableBody>
      </Table>
    )

    const caption = container.querySelector('caption')
    expect(caption).toBeInTheDocument()
    expect(caption).toHaveClass('mt-4', 'text-sm', 'text-zinc-500')
    expect(screen.getByText('Table Caption Text')).toBeInTheDocument()
  })
})

describe('Full table integration', () => {
  it('renders complete table with all components', () => {
    render(
      <Table>
        <TableCaption>User Data Table</TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Email</TableHead>
            <TableHead>Role</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow>
            <TableCell>John Doe</TableCell>
            <TableCell>john@example.com</TableCell>
            <TableCell>Admin</TableCell>
          </TableRow>
          <TableRow>
            <TableCell>Jane Smith</TableCell>
            <TableCell>jane@example.com</TableCell>
            <TableCell>User</TableCell>
          </TableRow>
        </TableBody>
        <TableFooter>
          <TableRow>
            <TableCell colSpan={3}>Total: 2 users</TableCell>
          </TableRow>
        </TableFooter>
      </Table>
    )

    // Check caption
    expect(screen.getByText('User Data Table')).toBeInTheDocument()

    // Check headers
    expect(screen.getByText('Name')).toBeInTheDocument()
    expect(screen.getByText('Email')).toBeInTheDocument()
    expect(screen.getByText('Role')).toBeInTheDocument()

    // Check body content
    expect(screen.getByText('John Doe')).toBeInTheDocument()
    expect(screen.getByText('john@example.com')).toBeInTheDocument()
    expect(screen.getByText('Admin')).toBeInTheDocument()
    expect(screen.getByText('Jane Smith')).toBeInTheDocument()
    expect(screen.getByText('jane@example.com')).toBeInTheDocument()
    expect(screen.getByText('User')).toBeInTheDocument()

    // Check footer
    expect(screen.getByText('Total: 2 users')).toBeInTheDocument()
  })

  it('all components have correct display names', () => {
    expect(Table.displayName).toBe('Table')
    expect(TableHeader.displayName).toBe('TableHeader')
    expect(TableBody.displayName).toBe('TableBody')
    expect(TableFooter.displayName).toBe('TableFooter')
    expect(TableRow.displayName).toBe('TableRow')
    expect(TableHead.displayName).toBe('TableHead')
    expect(TableCell.displayName).toBe('TableCell')
    expect(TableCaption.displayName).toBe('TableCaption')
  })
})
