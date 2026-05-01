/**
 * @jest-environment jsdom
 *
 * Branch coverage for DataImport - 5 uncovered branches.
 */

import '@testing-library/jest-dom'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { DataImport } from '../DataImport'

jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (key: string, vars?: any) => key }),
}))

jest.mock('@/stores/projectStore', () => ({
  useProjectStore: () => ({
    importData: jest.fn().mockResolvedValue({}),
    loading: false,
  }),
}))

jest.mock('react-dropzone', () => ({
  useDropzone: ({ onDrop, disabled }: any) => ({
    getRootProps: () => ({ 'data-testid': 'dropzone' }),
    getInputProps: () => ({ 'data-testid': 'file-input' }),
    isDragActive: false,
    acceptedFiles: [],
  }),
}))

jest.mock('@heroicons/react/24/outline', () => ({
  CheckCircleIcon: (props: any) => <svg {...props} />,
  ClipboardDocumentIcon: (props: any) => <svg {...props} />,
  CloudArrowUpIcon: (props: any) => <svg {...props} />,
}))

jest.mock('@/components/ui/alert', () => ({
  Alert: ({ children, className }: any) => <div className={className}>{children}</div>,
  AlertDescription: ({ children }: any) => <div>{children}</div>,
}))

jest.mock('@/components/ui/badge', () => ({
  Badge: ({ children }: any) => <span>{children}</span>,
}))

jest.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled }: any) => (
    <button onClick={onClick} disabled={disabled}>{children}</button>
  ),
}))

jest.mock('@/components/ui/card', () => ({
  Card: ({ children }: any) => <div>{children}</div>,
  CardContent: ({ children }: any) => <div>{children}</div>,
  CardDescription: ({ children }: any) => <div>{children}</div>,
  CardHeader: ({ children }: any) => <div>{children}</div>,
  CardTitle: ({ children }: any) => <h2>{children}</h2>,
}))

jest.mock('@/components/ui/tabs', () => ({
  Tabs: ({ children }: any) => <div>{children}</div>,
  TabsContent: ({ children, value }: any) => <div data-tab={value}>{children}</div>,
  TabsList: ({ children }: any) => <div>{children}</div>,
  TabsTrigger: ({ children, value }: any) => <button data-value={value}>{children}</button>,
}))

jest.mock('@/components/ui/textarea', () => ({
  Textarea: (props: any) => <textarea {...props} />,
}))

describe('DataImport', () => {
  it('renders with project id', () => {
    render(<DataImport projectId="p1" />)
    expect(screen.getByText('projects.dataImport.title')).toBeInTheDocument()
  })

  it('renders with onComplete callback', () => {
    render(<DataImport projectId="p1" onComplete={jest.fn()} />)
    expect(screen.getByText('projects.dataImport.title')).toBeInTheDocument()
  })

  it('renders dropzone area', () => {
    render(<DataImport projectId="p1" />)
    expect(screen.getByTestId('dropzone')).toBeInTheDocument()
  })

  it('shows format badges', () => {
    render(<DataImport projectId="p1" />)
    expect(screen.getByText('JSON')).toBeInTheDocument()
    expect(screen.getByText('CSV')).toBeInTheDocument()
    expect(screen.getByText('TSV')).toBeInTheDocument()
    expect(screen.getByText('TXT')).toBeInTheDocument()
  })

  it('renders paste tab', () => {
    render(<DataImport projectId="p1" />)
    expect(screen.getByText('projects.dataImport.pasteData')).toBeInTheDocument()
  })
})
