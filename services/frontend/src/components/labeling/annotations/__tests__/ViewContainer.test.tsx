/**
 * Comprehensive tests for ViewContainer component
 * Tests content rendering, layout handling, style parsing, and scroll behavior
 */

/**
 * @jest-environment jsdom
 */

import '@testing-library/jest-dom'
import { render, screen } from '@testing-library/react'

// Import the component
import ViewContainer from '../ViewContainer'

describe('ViewContainer', () => {
  const defaultConfig = {
    type: 'View',
    name: 'view',
    props: {},
    children: [],
  }

  const defaultProps = {
    config: defaultConfig,
    taskData: { text: 'Sample text' },
    value: null,
    onChange: jest.fn(),
    onAnnotation: jest.fn(),
  }

  describe('Basic Rendering', () => {
    it('renders container element', () => {
      render(<ViewContainer {...defaultProps} />)

      const container = document.querySelector('.view-container')
      expect(container).toBeInTheDocument()
    })

    it('renders children content', () => {
      render(
        <ViewContainer {...defaultProps}>
          <div>Child Content</div>
        </ViewContainer>
      )

      expect(screen.getByText('Child Content')).toBeInTheDocument()
    })

    it('renders multiple children', () => {
      render(
        <ViewContainer {...defaultProps}>
          <div>First Child</div>
          <div>Second Child</div>
          <div>Third Child</div>
        </ViewContainer>
      )

      expect(screen.getByText('First Child')).toBeInTheDocument()
      expect(screen.getByText('Second Child')).toBeInTheDocument()
      expect(screen.getByText('Third Child')).toBeInTheDocument()
    })

    it('renders without children', () => {
      render(<ViewContainer {...defaultProps} />)

      const container = document.querySelector('.view-container')
      expect(container).toBeEmptyDOMElement()
    })

    it('renders nested ViewContainer components', () => {
      render(
        <ViewContainer {...defaultProps}>
          <ViewContainer {...defaultProps}>
            <div>Nested Content</div>
          </ViewContainer>
        </ViewContainer>
      )

      expect(screen.getByText('Nested Content')).toBeInTheDocument()
    })
  })

  describe('Hidden Property', () => {
    it('renders when hidden is false', () => {
      const config = {
        ...defaultConfig,
        props: { hidden: 'false' },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toBeInTheDocument()
    })

    it('does not render when hidden is true', () => {
      const config = {
        ...defaultConfig,
        props: { hidden: 'true' },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).not.toBeInTheDocument()
    })

    it('renders by default when hidden not specified', () => {
      render(<ViewContainer {...defaultProps} />)

      const container = document.querySelector('.view-container')
      expect(container).toBeInTheDocument()
    })

    it('hides children when hidden is true', () => {
      const config = {
        ...defaultConfig,
        props: { hidden: 'true' },
      }

      render(
        <ViewContainer {...defaultProps} config={config}>
          <div>Should Not Render</div>
        </ViewContainer>
      )

      expect(screen.queryByText('Should Not Render')).not.toBeInTheDocument()
    })
  })

  describe('ClassName Property', () => {
    it('applies custom className', () => {
      const config = {
        ...defaultConfig,
        props: { className: 'custom-class' },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toHaveClass('custom-class')
    })

    it('applies multiple custom classes', () => {
      const config = {
        ...defaultConfig,
        props: { className: 'class-one class-two class-three' },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toHaveClass('class-one', 'class-two', 'class-three')
    })

    it('maintains view-container class with custom className', () => {
      const config = {
        ...defaultConfig,
        props: { className: 'extra-class' },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toHaveClass('view-container', 'extra-class')
    })

    it('renders without custom className', () => {
      render(<ViewContainer {...defaultProps} />)

      const container = document.querySelector('.view-container')
      expect(container).toHaveClass('view-container')
    })
  })

  describe('Style String Parsing', () => {
    it('parses simple style string', () => {
      const config = {
        ...defaultConfig,
        props: { style: 'color: #ff0000' },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toHaveStyle({ color: '#ff0000' })
    })

    it('parses multiple style properties', () => {
      const config = {
        ...defaultConfig,
        props: { style: 'color: #0000ff; background: #ffff00; padding: 10' },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toHaveStyle({
        color: '#0000ff',
        background: '#ffff00',
        padding: '10px',
      })
    })

    it('converts kebab-case to camelCase', () => {
      const config = {
        ...defaultConfig,
        props: { style: 'background-color: #00ff00; font-size: 16px' },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toHaveStyle({
        backgroundColor: '#00ff00',
        fontSize: '16px',
      })
    })

    it('handles numeric values for sizing properties', () => {
      const config = {
        ...defaultConfig,
        props: { style: 'width: 200; height: 100; margin: 15' },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toHaveStyle({
        width: '200px',
        height: '100px',
        margin: '15px',
      })
    })

    it('preserves non-numeric values', () => {
      const config = {
        ...defaultConfig,
        props: { style: 'width: 50%; display: flex' },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toHaveStyle({
        width: '50%',
        display: 'flex',
      })
    })

    it('handles empty style string', () => {
      const config = {
        ...defaultConfig,
        props: { style: '' },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toBeInTheDocument()
    })

    it('handles style with trailing semicolon', () => {
      const config = {
        ...defaultConfig,
        props: { style: 'color: #ff0000;' },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toHaveStyle({ color: '#ff0000' })
    })

    it('handles style without spaces', () => {
      const config = {
        ...defaultConfig,
        props: { style: 'color:#ff0000;background:#0000ff' },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toHaveStyle({ color: '#ff0000', background: '#0000ff' })
    })
  })

  describe('Style Object Support', () => {
    it('accepts style as object', () => {
      const config = {
        ...defaultConfig,
        props: {
          style: { color: '#800080', fontSize: '20px' },
        },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toHaveStyle({ color: '#800080', fontSize: '20px' })
    })

    it('handles complex style object', () => {
      const config = {
        ...defaultConfig,
        props: {
          style: {
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            padding: '20px',
          },
        },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toHaveStyle({
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        padding: '20px',
      })
    })
  })

  describe('Layout Patterns', () => {
    it('applies flexbox layout', () => {
      const config = {
        ...defaultConfig,
        props: {
          style: 'display: flex; flex-direction: row; gap: 10',
        },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toHaveStyle({
        display: 'flex',
        flexDirection: 'row',
      })
    })

    it('applies grid layout', () => {
      const config = {
        ...defaultConfig,
        props: {
          style: 'display: grid; grid-template-columns: 1fr 1fr',
        },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toHaveStyle({
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
      })
    })

    it('applies spacing styles', () => {
      const config = {
        ...defaultConfig,
        props: {
          style: 'padding: 20; margin: 10',
        },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toHaveStyle({
        padding: '20px',
        margin: '10px',
      })
    })

    it('applies border styles', () => {
      const config = {
        ...defaultConfig,
        props: {
          style: 'border: 1px solid black; border-radius: 8px',
        },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toHaveStyle({
        border: '1px solid black',
        borderRadius: '8px',
      })
    })
  })

  describe('Scroll Behavior', () => {
    it('applies overflow styles', () => {
      const config = {
        ...defaultConfig,
        props: {
          style: 'overflow: auto',
        },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toHaveStyle({ overflow: 'auto' })
    })

    it('applies overflow-x and overflow-y', () => {
      const config = {
        ...defaultConfig,
        props: {
          style: 'overflow-x: hidden; overflow-y: scroll',
        },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toHaveStyle({
        overflowX: 'hidden',
        overflowY: 'scroll',
      })
    })

    it('applies max-height for scrollable container', () => {
      const config = {
        ...defaultConfig,
        props: {
          style: 'max-height: 300; overflow-y: auto',
        },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toHaveStyle({
        maxHeight: '300px',
        overflowY: 'auto',
      })
    })
  })

  describe('Edge Cases', () => {
    it('handles invalid style property', () => {
      const config = {
        ...defaultConfig,
        props: {
          style: 'invalid-property: value',
        },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toBeInTheDocument()
    })

    it('handles malformed style string', () => {
      const config = {
        ...defaultConfig,
        props: {
          style: 'color red background blue',
        },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toBeInTheDocument()
    })

    it('handles style with only property name', () => {
      const config = {
        ...defaultConfig,
        props: {
          style: 'color:',
        },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toBeInTheDocument()
    })

    it('handles style with only value', () => {
      const config = {
        ...defaultConfig,
        props: {
          style: ': red',
        },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toBeInTheDocument()
    })

    it('handles very long style string', () => {
      const longStyle = Array(100).fill('color: #ff0000').join('; ')

      const config = {
        ...defaultConfig,
        props: { style: longStyle },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toHaveStyle({ color: '#ff0000' })
    })
  })

  describe('Complex Layouts', () => {
    it('renders complex nested structure', () => {
      render(
        <ViewContainer {...defaultProps}>
          <ViewContainer
            {...defaultProps}
            config={{
              ...defaultConfig,
              props: { style: 'display: flex' },
            }}
          >
            <div>Column 1</div>
            <div>Column 2</div>
          </ViewContainer>
          <ViewContainer
            {...defaultProps}
            config={{
              ...defaultConfig,
              props: { style: 'padding: 20' },
            }}
          >
            <div>Footer</div>
          </ViewContainer>
        </ViewContainer>
      )

      expect(screen.getByText('Column 1')).toBeInTheDocument()
      expect(screen.getByText('Column 2')).toBeInTheDocument()
      expect(screen.getByText('Footer')).toBeInTheDocument()
    })

    it('combines className and style', () => {
      const config = {
        ...defaultConfig,
        props: {
          className: 'custom-layout',
          style: 'padding: 15px; background: #ffffff',
        },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toHaveClass('view-container', 'custom-layout')
      expect(container).toHaveStyle({
        padding: '15px',
        background: '#ffffff',
      })
    })

    it('handles all props together', () => {
      const config = {
        ...defaultConfig,
        props: {
          className: 'complete-example',
          style: 'margin: 10px; color: #000080',
          hidden: 'false',
        },
      }

      render(
        <ViewContainer {...defaultProps} config={config}>
          <div>Complete Test</div>
        </ViewContainer>
      )

      const container = document.querySelector('.view-container')
      expect(container).toBeInTheDocument()
      expect(container).toHaveClass('complete-example')
      expect(container).toHaveStyle({ margin: '10px', color: '#000080' })
      expect(screen.getByText('Complete Test')).toBeInTheDocument()
    })
  })

  describe('Responsiveness', () => {
    it('applies responsive width styles', () => {
      const config = {
        ...defaultConfig,
        props: {
          style: 'width: 100%; max-width: 1200',
        },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toHaveStyle({
        width: '100%',
        maxWidth: '1200px',
      })
    })

    it('applies min and max dimensions', () => {
      const config = {
        ...defaultConfig,
        props: {
          style:
            'min-width: 300; max-width: 800; min-height: 200; max-height: 600',
        },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toHaveStyle({
        minWidth: '300px',
        maxWidth: '800px',
        minHeight: '200px',
        maxHeight: '600px',
      })
    })
  })

  describe('Multiple Instances', () => {
    it('renders multiple ViewContainer components independently', () => {
      render(
        <div>
          <ViewContainer
            {...defaultProps}
            config={{
              ...defaultConfig,
              props: { className: 'container-1', style: 'color: #ff0000' },
            }}
          >
            <div>First Container</div>
          </ViewContainer>
          <ViewContainer
            {...defaultProps}
            config={{
              ...defaultConfig,
              props: { className: 'container-2', style: 'color: #0000ff' },
            }}
          >
            <div>Second Container</div>
          </ViewContainer>
        </div>
      )

      const containers = document.querySelectorAll('.view-container')
      expect(containers).toHaveLength(2)

      expect(containers[0]).toHaveClass('container-1')
      expect(containers[0]).toHaveStyle({ color: '#ff0000' })

      expect(containers[1]).toHaveClass('container-2')
      expect(containers[1]).toHaveStyle({ color: '#0000ff' })
    })

    it('handles deeply nested ViewContainers', () => {
      render(
        <ViewContainer {...defaultProps}>
          <ViewContainer {...defaultProps}>
            <ViewContainer {...defaultProps}>
              <ViewContainer {...defaultProps}>
                <div>Deep Content</div>
              </ViewContainer>
            </ViewContainer>
          </ViewContainer>
        </ViewContainer>
      )

      const containers = document.querySelectorAll('.view-container')
      expect(containers).toHaveLength(4)
      expect(screen.getByText('Deep Content')).toBeInTheDocument()
    })
  })

  describe('Special CSS Properties', () => {
    it('handles position properties', () => {
      const config = {
        ...defaultConfig,
        props: {
          style: 'position: absolute; top: 10px; left: 20px',
        },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toHaveStyle({
        position: 'absolute',
        top: '10px',
        left: '20px',
      })
    })

    it('handles z-index', () => {
      const config = {
        ...defaultConfig,
        props: {
          style: 'z-index: 100',
        },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toHaveStyle({ zIndex: '100' })
    })

    it('handles opacity and transform', () => {
      const config = {
        ...defaultConfig,
        props: {
          style: 'opacity: 0.8; transform: scale(1.1)',
        },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toHaveStyle({
        opacity: '0.8',
        transform: 'scale(1.1)',
      })
    })

    it('handles box-shadow and text-shadow', () => {
      const config = {
        ...defaultConfig,
        props: {
          style: 'box-shadow: 0 2px 4px rgba(0,0,0,0.1)',
        },
      }

      render(<ViewContainer {...defaultProps} config={config} />)

      const container = document.querySelector('.view-container')
      expect(container).toHaveStyle({
        boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
      })
    })
  })
})
