import { render, screen } from '@testing-library/react'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '../card'

describe('Card Components', () => {
  describe('Card', () => {
    it('renders correctly with children', () => {
      render(
        <Card>
          <div data-testid="card-child">Card content</div>
        </Card>
      )

      const card = screen.getByTestId('card-child').parentElement
      expect(card).toBeInTheDocument()
      expect(screen.getByTestId('card-child')).toBeInTheDocument()
    })

    it('applies default card styles', () => {
      render(
        <Card data-testid="card">
          <div>Content</div>
        </Card>
      )

      const card = screen.getByTestId('card')
      expect(card).toHaveClass(
        'rounded-lg',
        'border',
        'border-zinc-200',
        'bg-white',
        'shadow-sm',
        'dark:border-zinc-800',
        'dark:bg-zinc-900'
      )
    })

    it('applies custom className', () => {
      render(
        <Card className="custom-class" data-testid="card">
          <div>Content</div>
        </Card>
      )

      const card = screen.getByTestId('card')
      expect(card).toHaveClass('custom-class')
      expect(card).toHaveClass('rounded-lg') // Default styles still applied
    })

    it('forwards HTML div attributes', () => {
      render(
        <Card
          data-testid="card"
          id="card-id"
          role="region"
          aria-label="Card section"
        >
          <div>Content</div>
        </Card>
      )

      const card = screen.getByTestId('card')
      expect(card).toHaveAttribute('id', 'card-id')
      expect(card).toHaveAttribute('role', 'region')
      expect(card).toHaveAttribute('aria-label', 'Card section')
    })
  })

  describe('CardHeader', () => {
    it('renders correctly with children', () => {
      render(
        <CardHeader>
          <div data-testid="header-child">Header content</div>
        </CardHeader>
      )

      const header = screen.getByTestId('header-child').parentElement
      expect(header).toBeInTheDocument()
      expect(screen.getByTestId('header-child')).toBeInTheDocument()
    })

    it('applies default header styles', () => {
      render(
        <CardHeader data-testid="header">
          <div>Header</div>
        </CardHeader>
      )

      const header = screen.getByTestId('header')
      expect(header).toHaveClass(
        'px-6',
        'py-4',
        'border-b',
        'border-zinc-200',
        'dark:border-zinc-800'
      )
    })

    it('applies custom className', () => {
      render(
        <CardHeader className="custom-header" data-testid="header">
          <div>Header</div>
        </CardHeader>
      )

      const header = screen.getByTestId('header')
      expect(header).toHaveClass('custom-header')
      expect(header).toHaveClass('px-6') // Default styles still applied
    })
  })

  describe('CardTitle', () => {
    it('renders as h3 element', () => {
      render(<CardTitle>Title text</CardTitle>)

      const title = screen.getByRole('heading', { level: 3 })
      expect(title).toBeInTheDocument()
      expect(title).toHaveTextContent('Title text')
    })

    it('applies default title styles', () => {
      render(<CardTitle data-testid="title">Title</CardTitle>)

      const title = screen.getByTestId('title')
      expect(title).toHaveClass(
        'text-lg',
        'font-semibold',
        'text-zinc-900',
        'dark:text-zinc-100'
      )
    })

    it('applies custom className', () => {
      render(
        <CardTitle className="custom-title" data-testid="title">
          Title
        </CardTitle>
      )

      const title = screen.getByTestId('title')
      expect(title).toHaveClass('custom-title')
      expect(title).toHaveClass('text-lg') // Default styles still applied
    })

    it('forwards HTML heading attributes', () => {
      render(
        <CardTitle data-testid="title" id="title-id" aria-level="3">
          Title
        </CardTitle>
      )

      const title = screen.getByTestId('title')
      expect(title).toHaveAttribute('id', 'title-id')
      expect(title).toHaveAttribute('aria-level', '3')
    })
  })

  describe('CardDescription', () => {
    it('renders as p element', () => {
      render(<CardDescription>Description text</CardDescription>)

      const description = screen.getByText('Description text')
      expect(description).toBeInTheDocument()
      expect(description.tagName).toBe('P')
    })

    it('applies default description styles', () => {
      render(
        <CardDescription data-testid="description">Description</CardDescription>
      )

      const description = screen.getByTestId('description')
      expect(description).toHaveClass(
        'text-sm',
        'text-zinc-600',
        'dark:text-zinc-400'
      )
    })

    it('applies custom className', () => {
      render(
        <CardDescription className="custom-desc" data-testid="description">
          Description
        </CardDescription>
      )

      const description = screen.getByTestId('description')
      expect(description).toHaveClass('custom-desc')
      expect(description).toHaveClass('text-sm') // Default styles still applied
    })
  })

  describe('CardContent', () => {
    it('renders correctly with children', () => {
      render(
        <CardContent>
          <div data-testid="content-child">Content here</div>
        </CardContent>
      )

      const content = screen.getByTestId('content-child').parentElement
      expect(content).toBeInTheDocument()
      expect(screen.getByTestId('content-child')).toBeInTheDocument()
    })

    it('applies default content styles', () => {
      render(
        <CardContent data-testid="content">
          <div>Content</div>
        </CardContent>
      )

      const content = screen.getByTestId('content')
      expect(content).toHaveClass('px-6', 'py-4')
    })

    it('applies custom className', () => {
      render(
        <CardContent className="custom-content" data-testid="content">
          <div>Content</div>
        </CardContent>
      )

      const content = screen.getByTestId('content')
      expect(content).toHaveClass('custom-content')
      expect(content).toHaveClass('px-6') // Default styles still applied
    })
  })

  describe('CardFooter', () => {
    it('renders correctly with children', () => {
      render(
        <CardFooter>
          <div data-testid="footer-child">Footer content</div>
        </CardFooter>
      )

      const footer = screen.getByTestId('footer-child').parentElement
      expect(footer).toBeInTheDocument()
      expect(screen.getByTestId('footer-child')).toBeInTheDocument()
    })

    it('applies default footer styles', () => {
      render(
        <CardFooter data-testid="footer">
          <div>Footer</div>
        </CardFooter>
      )

      const footer = screen.getByTestId('footer')
      expect(footer).toHaveClass(
        'px-6',
        'py-4',
        'border-t',
        'border-zinc-200',
        'dark:border-zinc-800'
      )
    })

    it('applies custom className', () => {
      render(
        <CardFooter className="custom-footer" data-testid="footer">
          <div>Footer</div>
        </CardFooter>
      )

      const footer = screen.getByTestId('footer')
      expect(footer).toHaveClass('custom-footer')
      expect(footer).toHaveClass('px-6') // Default styles still applied
    })
  })

  describe('Full Card composition', () => {
    it('renders complete card structure', () => {
      render(
        <Card data-testid="full-card">
          <CardHeader data-testid="full-header">
            <CardTitle data-testid="full-title">Card Title</CardTitle>
            <CardDescription data-testid="full-description">
              Card description text
            </CardDescription>
          </CardHeader>
          <CardContent data-testid="full-content">
            <p>Main card content goes here</p>
          </CardContent>
          <CardFooter data-testid="full-footer">
            <button>Action Button</button>
          </CardFooter>
        </Card>
      )

      expect(screen.getByTestId('full-card')).toBeInTheDocument()
      expect(screen.getByTestId('full-header')).toBeInTheDocument()
      expect(screen.getByTestId('full-title')).toBeInTheDocument()
      expect(screen.getByTestId('full-description')).toBeInTheDocument()
      expect(screen.getByTestId('full-content')).toBeInTheDocument()
      expect(screen.getByTestId('full-footer')).toBeInTheDocument()

      expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent(
        'Card Title'
      )
      expect(screen.getByText('Card description text')).toBeInTheDocument()
      expect(
        screen.getByText('Main card content goes here')
      ).toBeInTheDocument()
      expect(
        screen.getByRole('button', { name: 'Action Button' })
      ).toBeInTheDocument()
    })

    it('works with minimal composition', () => {
      render(
        <Card data-testid="minimal-card">
          <CardContent data-testid="minimal-content">
            <p>Simple card content</p>
          </CardContent>
        </Card>
      )

      expect(screen.getByTestId('minimal-card')).toBeInTheDocument()
      expect(screen.getByTestId('minimal-content')).toBeInTheDocument()
      expect(screen.getByText('Simple card content')).toBeInTheDocument()
    })
  })

  describe('Accessibility', () => {
    it('maintains semantic structure', () => {
      render(
        <Card>
          <CardHeader>
            <CardTitle>Accessible Title</CardTitle>
            <CardDescription>Accessible description</CardDescription>
          </CardHeader>
          <CardContent>
            <p>Accessible content</p>
          </CardContent>
        </Card>
      )

      const heading = screen.getByRole('heading', { level: 3 })
      expect(heading).toHaveTextContent('Accessible Title')

      const description = screen.getByText('Accessible description')
      expect(description.tagName).toBe('P')
    })

    it('supports ARIA attributes', () => {
      render(
        <Card role="article" aria-labelledby="card-title">
          <CardHeader>
            <CardTitle id="card-title">Article Title</CardTitle>
          </CardHeader>
          <CardContent>
            <p>Article content</p>
          </CardContent>
        </Card>
      )

      const card = screen.getByRole('article')
      expect(card).toHaveAttribute('aria-labelledby', 'card-title')

      const title = screen.getByRole('heading')
      expect(title).toHaveAttribute('id', 'card-title')
    })
  })

  describe('Dark mode support', () => {
    it('includes dark mode classes for all components', () => {
      render(
        <Card data-testid="dark-card" className="dark">
          <CardHeader data-testid="dark-header">
            <CardTitle data-testid="dark-title">Title</CardTitle>
            <CardDescription data-testid="dark-description">
              Description
            </CardDescription>
          </CardHeader>
          <CardFooter data-testid="dark-footer">Footer</CardFooter>
        </Card>
      )

      const card = screen.getByTestId('dark-card')
      const header = screen.getByTestId('dark-header')
      const title = screen.getByTestId('dark-title')
      const description = screen.getByTestId('dark-description')
      const footer = screen.getByTestId('dark-footer')

      expect(card).toHaveClass('dark:border-zinc-800', 'dark:bg-zinc-900')
      expect(header).toHaveClass('dark:border-zinc-800')
      expect(title).toHaveClass('dark:text-zinc-100')
      expect(description).toHaveClass('dark:text-zinc-400')
      expect(footer).toHaveClass('dark:border-zinc-800')
    })
  })

  describe('Edge cases', () => {
    it('handles empty children', () => {
      render(<Card data-testid="empty-card"></Card>)

      const card = screen.getByTestId('empty-card')
      expect(card).toBeInTheDocument()
      expect(card).toHaveTextContent('')
    })

    it('handles complex nested children', () => {
      render(
        <Card>
          <CardContent>
            <div>
              <span>Nested</span>
              <div>
                <p>Deep nesting</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )

      expect(screen.getByText('Nested')).toBeInTheDocument()
      expect(screen.getByText('Deep nesting')).toBeInTheDocument()
    })

    it('handles multiple instances', () => {
      render(
        <div>
          <Card data-testid="card-1">
            <CardTitle>First Card</CardTitle>
          </Card>
          <Card data-testid="card-2">
            <CardTitle>Second Card</CardTitle>
          </Card>
        </div>
      )

      expect(screen.getByTestId('card-1')).toBeInTheDocument()
      expect(screen.getByTestId('card-2')).toBeInTheDocument()
      expect(screen.getByText('First Card')).toBeInTheDocument()
      expect(screen.getByText('Second Card')).toBeInTheDocument()
    })
  })
})
