import { ExtractTextError, filesAPI } from '../files'

jest.mock('@/lib/api', () => ({
  __esModule: true,
  default: { post: jest.fn() },
}))

const apiClient = require('@/lib/api').default

describe('filesAPI.extractText', () => {
  beforeEach(() => jest.clearAllMocks())

  it('POSTs the file as multipart to /files/extract-text', async () => {
    apiClient.post.mockResolvedValue({ text: 'Hallo', source_format: 'pdf', warnings: [] })
    const file = new File(['x'], 'a.pdf', { type: 'application/pdf' })
    await expect(filesAPI.extractText(file)).resolves.toEqual({
      text: 'Hallo', source_format: 'pdf', warnings: [],
    })
    const [url, form] = apiClient.post.mock.calls[0]
    expect(url).toBe('/files/extract-text')
    expect(form).toBeInstanceOf(FormData)
    expect(form.get('file')).toBe(file)
  })

  it('maps a structured 4xx body to ExtractTextError and rethrows others', async () => {
    apiClient.post.mockRejectedValueOnce({ data: { code: 'image_only_pdf', message: 'Nur Bilder' } })
    await expect(filesAPI.extractText(new File([''], 'b.pdf'))).rejects.toMatchObject({
      name: 'ExtractTextError', code: 'image_only_pdf', message: 'Nur Bilder',
    })
    const plain = new Error('network')
    apiClient.post.mockRejectedValueOnce(plain)
    await expect(filesAPI.extractText(new File([''], 'c.pdf'))).rejects.toBe(plain)
    expect(new ExtractTextError('x', 'y')).toBeInstanceOf(Error)
  })
})
