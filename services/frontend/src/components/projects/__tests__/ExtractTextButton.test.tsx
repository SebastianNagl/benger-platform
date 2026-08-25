/**
 * @jest-environment jsdom
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ExtractTextButton } from '../ExtractTextButton'

const mockAddToast = jest.fn()
jest.mock('@/components/shared/Toast', () => ({ useToast: () => ({ addToast: mockAddToast }) }))
jest.mock('@/contexts/I18nContext', () => ({
  useI18n: () => ({ t: (k: string, d?: any) => (typeof d === 'string' ? d : k) }),
}))
const mockExtract = jest.fn()
jest.mock('@/lib/api/files', () => ({
  EXTRACTABLE_ACCEPT: '.pdf,.docx,.txt,.md',
  filesAPI: { extractText: (...a: any[]) => mockExtract(...a) },
}))

const pick = (file: File) => {
  const input = screen.getByTestId('extract-text-input') as HTMLInputElement
  Object.defineProperty(input, 'files', { value: [file], configurable: true })
  fireEvent.change(input)
}

describe('ExtractTextButton', () => {
  beforeEach(() => jest.clearAllMocks())

  it('extracts and hands the text to onText; warnings toast', async () => {
    mockExtract.mockResolvedValue({ text: 'Sachverhalt…', source_format: 'pdf', warnings: ['Seite 3 übersprungen'] })
    const onText = jest.fn()
    render(<ExtractTextButton onText={onText} />)
    fireEvent.click(screen.getByTestId('extract-text-button'))
    pick(new File(['x'], 'fall.pdf'))
    await waitFor(() => expect(onText).toHaveBeenCalledWith('Sachverhalt…', 'fall.pdf'))
    expect(mockAddToast).toHaveBeenCalledWith('Seite 3 übersprungen', 'warning')
  })

  it('failure toasts the error and does not call onText', async () => {
    mockExtract.mockRejectedValue(new Error('Nur Bilder'))
    const onText = jest.fn()
    render(<ExtractTextButton onText={onText} />)
    pick(new File(['x'], 'scan.pdf'))
    await waitFor(() => expect(mockAddToast).toHaveBeenCalledWith('Nur Bilder', 'error'))
    expect(onText).not.toHaveBeenCalled()
  })
})
