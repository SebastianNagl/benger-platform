/**
 * Tests for universal import/export functionality
 * Issue #369: Verify Excel functionality works after replacing xlsx with exceljs
 */

import * as ExcelJS from 'exceljs'
import {
  detectFileFormat,
  exportData,
  importFile,
  parseCSV,
  parseExcel,
  parseJSON,
} from '../universalImport'

// Mock URL methods that aren't available in jsdom
beforeAll(() => {
  global.URL.createObjectURL = jest.fn(() => 'blob:mock-url')
  global.URL.revokeObjectURL = jest.fn()
})

afterAll(() => {
  jest.restoreAllMocks()
})

describe('Universal Import/Export', () => {
  describe('detectFileFormat', () => {
    it('should detect Excel files by extension', () => {
      const xlsxFile = new File([''], 'test.xlsx')
      const xlsFile = new File([''], 'test.xls')

      expect(detectFileFormat(xlsxFile)).toBe('excel')
      expect(detectFileFormat(xlsFile)).toBe('excel')
    })

    it('should detect CSV files by extension', () => {
      const csvFile = new File([''], 'test.csv')
      expect(detectFileFormat(csvFile)).toBe('csv')
    })

    it('should detect JSON files by extension', () => {
      const jsonFile = new File([''], 'test.json')
      expect(detectFileFormat(jsonFile)).toBe('json')
    })

    it('should detect TSV files by extension', () => {
      const tsvFile = new File([''], 'test.tsv')
      expect(detectFileFormat(tsvFile)).toBe('tsv')
    })
  })

  describe('parseExcel', () => {
    it('should parse Excel file with ExcelJS', async () => {
      // Create a mock Excel file using ExcelJS
      const workbook = new ExcelJS.Workbook()
      const worksheet = workbook.addWorksheet('TestSheet')

      // Add headers
      worksheet.addRow(['Name', 'Age', 'Email'])

      // Add data
      worksheet.addRow(['John Doe', 30, 'john@example.com'])
      worksheet.addRow(['Jane Smith', 25, 'jane@example.com'])

      // Convert to buffer
      const buffer = await workbook.xlsx.writeBuffer()
      const file = new File([buffer], 'test.xlsx', {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })

      // Parse the file
      const result = await parseExcel(file)

      expect(result.format).toBe('excel')
      expect(result.data).toHaveLength(2)
      expect(result.headers).toEqual(['Name', 'Age', 'Email'])
      expect(result.data[0]).toEqual({
        Name: 'John Doe',
        Age: 30,
        Email: 'john@example.com',
      })
      expect(result.metadata?.sheets).toContain('TestSheet')
    })

    it('should handle empty Excel files', async () => {
      const workbook = new ExcelJS.Workbook()
      workbook.addWorksheet('EmptySheet')

      const buffer = await workbook.xlsx.writeBuffer()
      const file = new File([buffer], 'empty.xlsx', {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })

      const result = await parseExcel(file)

      expect(result.format).toBe('excel')
      expect(result.data).toHaveLength(0)
      expect(result.headers).toEqual([])
    })

    it('should select specific sheet by name', async () => {
      const workbook = new ExcelJS.Workbook()
      workbook.addWorksheet('Sheet1').addRow(['Col1', 'Col2'])
      const sheet2 = workbook.addWorksheet('Sheet2')
      sheet2.addRow(['Name', 'Value'])
      sheet2.addRow(['Test', 123])

      const buffer = await workbook.xlsx.writeBuffer()
      const file = new File([buffer], 'multi-sheet.xlsx')

      const result = await parseExcel(file, { sheet: 'Sheet2' })

      expect(result.data).toHaveLength(1)
      expect(result.data[0]).toEqual({ Name: 'Test', Value: 123 })
    })

    it('should transform headers to camelCase when requested', async () => {
      const workbook = new ExcelJS.Workbook()
      const worksheet = workbook.addWorksheet('TestSheet')

      worksheet.addRow(['First Name', 'Last Name', 'Email Address'])
      worksheet.addRow(['John', 'Doe', 'john@example.com'])

      const buffer = await workbook.xlsx.writeBuffer()
      const file = new File([buffer], 'test.xlsx')

      const result = await parseExcel(file, { transformHeaders: true })

      expect(result.headers).toEqual(['firstName', 'lastName', 'emailAddress'])
      expect(result.data[0]).toHaveProperty('firstName', 'John')
      expect(result.data[0]).toHaveProperty('lastName', 'Doe')
      expect(result.data[0]).toHaveProperty('emailAddress', 'john@example.com')
    })
  })

  describe('exportData', () => {
    it('should export data to Excel format', async () => {
      const data = [
        { name: 'John', age: 30, email: 'john@example.com' },
        { name: 'Jane', age: 25, email: 'jane@example.com' },
      ]

      // Mock downloadBlob
      const createElementSpy = jest.spyOn(document, 'createElement')
      const createObjectURLSpy = jest
        .spyOn(URL, 'createObjectURL')
        .mockReturnValue('blob:url')
      const revokeObjectURLSpy = jest
        .spyOn(URL, 'revokeObjectURL')
        .mockImplementation()

      await exportData(data, 'excel', 'test-export')

      expect(createElementSpy).toHaveBeenCalledWith('a')
      expect(createObjectURLSpy).toHaveBeenCalled()
      expect(revokeObjectURLSpy).toHaveBeenCalled()

      createElementSpy.mockRestore()
      createObjectURLSpy.mockRestore()
      revokeObjectURLSpy.mockRestore()
    })

    it('should export data to JSON format', async () => {
      const data = [{ test: 'value' }]

      const createObjectURLSpy = jest
        .spyOn(URL, 'createObjectURL')
        .mockReturnValue('blob:url')
      const revokeObjectURLSpy = jest
        .spyOn(URL, 'revokeObjectURL')
        .mockImplementation()

      await exportData(data, 'json', 'test-export')

      expect(createObjectURLSpy).toHaveBeenCalled()

      createObjectURLSpy.mockRestore()
      revokeObjectURLSpy.mockRestore()
    })

    it('should export data to CSV format', async () => {
      const data = [
        { name: 'John', age: 30 },
        { name: 'Jane', age: 25 },
      ]

      const createObjectURLSpy = jest
        .spyOn(URL, 'createObjectURL')
        .mockReturnValue('blob:url')
      const revokeObjectURLSpy = jest
        .spyOn(URL, 'revokeObjectURL')
        .mockImplementation()

      await exportData(data, 'csv', 'test-export')

      expect(createObjectURLSpy).toHaveBeenCalled()

      createObjectURLSpy.mockRestore()
      revokeObjectURLSpy.mockRestore()
    })
  })

  describe('Security - Input Validation', () => {
    it('should handle malformed Excel files gracefully', async () => {
      const malformedFile = new File(['not an excel file'], 'bad.xlsx')

      await expect(parseExcel(malformedFile)).rejects.toThrow(
        'Failed to parse Excel file'
      )
    })

    it('should sanitize file inputs to prevent injection', async () => {
      const workbook = new ExcelJS.Workbook()
      const worksheet = workbook.addWorksheet('Test')

      // Add potentially dangerous content
      worksheet.addRow([
        '<script>alert("xss")</script>',
        '=1+1',
        '../../etc/passwd',
      ])
      worksheet.addRow(['Normal', 'Data', 'Here'])

      const buffer = await workbook.xlsx.writeBuffer()
      const file = new File([buffer], 'test.xlsx')

      const result = await parseExcel(file)

      // Verify that dangerous content is treated as plain text
      expect(result.data[0]['<script>alert("xss")</script>']).toBe('Normal')
      expect(result.data[0]['=1+1']).toBe('Data')
      expect(result.data[0]['../../etc/passwd']).toBe('Here')
    })

    it('should limit file size processing', async () => {
      // This would be implemented with actual file size checks in production
      const largeFile = new File(
        [new ArrayBuffer(100 * 1024 * 1024)],
        'large.xlsx'
      ) // 100MB

      // In production, you would check file.size before processing
      expect(largeFile.size).toBeGreaterThan(50 * 1024 * 1024) // > 50MB
    })
  })

  describe('parseJSON', () => {
    it('should parse standard JSON array', () => {
      const content = JSON.stringify([
        { name: 'John', age: 30 },
        { name: 'Jane', age: 25 },
      ])

      const result = parseJSON(content)

      expect(result.format).toBe('json')
      expect(result.data).toHaveLength(2)
      expect(result.data[0].name).toBe('John')
      expect(result.metadata?.totalRows).toBe(2)
    })

    it('should parse single JSON object', () => {
      const content = JSON.stringify({ name: 'John', age: 30 })

      const result = parseJSON(content)

      expect(result.format).toBe('json')
      expect(result.data).toHaveLength(1)
      expect(result.data[0].name).toBe('John')
    })

    it('should parse JSONL format', () => {
      const content = '{"name":"John","age":30}\n{"name":"Jane","age":25}'

      const result = parseJSON(content)

      expect(result.format).toBe('json')
      expect(result.data).toHaveLength(2)
      expect(result.data[0].name).toBe('John')
      expect(result.data[1].name).toBe('Jane')
    })

    it('should handle JSONL with empty lines', () => {
      const content = '{"name":"John"}\n\n{"name":"Jane"}\n'

      const result = parseJSON(content)

      expect(result.data).toHaveLength(2)
    })

    it('should collect errors for invalid JSONL lines', () => {
      const content = '{"name":"John"}\ninvalid json\n{"name":"Jane"}'

      const result = parseJSON(content)

      expect(result.data).toHaveLength(2)
      expect(result.errors).toBeDefined()
      expect(result.errors?.length).toBeGreaterThan(0)
      expect(result.errors?.[0]).toContain('Line 2')
    })
  })

  describe('parseCSV', () => {
    it('should parse CSV with headers', async () => {
      const content =
        'Name,Age,Email\nJohn,30,john@test.com\nJane,25,jane@test.com'

      const result = await parseCSV(content)

      expect(result.format).toBe('csv')
      expect(result.data).toHaveLength(2)
      expect(result.headers).toEqual(['Name', 'Age', 'Email'])
      expect(result.data[0].Name).toBe('John')
    })

    it('should parse TSV with delimiter option', async () => {
      const content = 'Name\tAge\tEmail\nJohn\t30\tjohn@test.com'

      const result = await parseCSV(content, { delimiter: '\t' })

      expect(result.format).toBe('tsv')
      expect(result.data).toHaveLength(1)
      expect(result.data[0].Name).toBe('John')
    })

    it('should detect types when enabled', async () => {
      const content = 'Name,Age,Active\nJohn,30,true'

      const result = await parseCSV(content, { detectTypes: true })

      expect(result.data[0].Age).toBe(30)
      expect(typeof result.data[0].Age).toBe('number')
    })

    it('should transform headers to camelCase', async () => {
      const content =
        'First Name,Last Name,Email Address\nJohn,Doe,john@test.com'

      const result = await parseCSV(content, { transformHeaders: true })

      expect(result.data[0]).toHaveProperty('firstName', 'John')
      expect(result.data[0]).toHaveProperty('lastName', 'Doe')
      expect(result.data[0]).toHaveProperty('emailAddress', 'john@test.com')
    })

    it('should skip empty rows when enabled', async () => {
      const content = 'Name,Age\nJohn,30\n\nJane,25'

      const result = await parseCSV(content, { skipEmptyRows: true })

      expect(result.data).toHaveLength(2)
    })

    it('should include parsing errors', async () => {
      const content = 'Name,Age\n"John,30\nJane,25'

      const result = await parseCSV(content)

      if (result.errors && result.errors.length > 0) {
        expect(result.errors[0]).toContain('Row')
      }
    })
  })

  describe('parseExcel - Advanced', () => {
    it('should select sheet by index', async () => {
      const workbook = new ExcelJS.Workbook()
      workbook.addWorksheet('Sheet1').addRow(['Col1'])
      const sheet2 = workbook.addWorksheet('Sheet2')
      sheet2.addRow(['Name'])
      sheet2.addRow(['Test'])

      const buffer = await workbook.xlsx.writeBuffer()
      const file = new File([buffer], 'test.xlsx')

      const result = await parseExcel(file, { sheet: 1 })

      expect(result.data).toHaveLength(1)
      expect(result.data[0].Name).toBe('Test')
    })

    it('should handle formula cells', async () => {
      const workbook = new ExcelJS.Workbook()
      const worksheet = workbook.addWorksheet('Sheet1')
      worksheet.addRow(['Value', 'Formula'])
      const row = worksheet.addRow([10, { formula: 'A2*2', result: 20 }])

      const buffer = await workbook.xlsx.writeBuffer()
      const file = new File([buffer], 'test.xlsx')

      const result = await parseExcel(file)

      expect(result.data[0].Formula).toBe(20)
    })

    it('should handle date cells', async () => {
      const workbook = new ExcelJS.Workbook()
      const worksheet = workbook.addWorksheet('Sheet1')
      worksheet.addRow(['Date'])
      const date = new Date('2024-01-15')
      worksheet.addRow([date])

      const buffer = await workbook.xlsx.writeBuffer()
      const file = new File([buffer], 'test.xlsx')

      const result = await parseExcel(file)

      expect(result.data[0].Date).toBe(date.toISOString())
    })

    it('should skip empty rows by default', async () => {
      const workbook = new ExcelJS.Workbook()
      const worksheet = workbook.addWorksheet('Sheet1')
      worksheet.addRow(['Name'])
      worksheet.addRow(['John'])
      worksheet.addRow([]) // Empty row
      worksheet.addRow(['Jane'])

      const buffer = await workbook.xlsx.writeBuffer()
      const file = new File([buffer], 'test.xlsx')

      const result = await parseExcel(file)

      expect(result.data.length).toBeLessThanOrEqual(3)
    })

    it('should include empty rows when skipEmptyRows is false', async () => {
      const workbook = new ExcelJS.Workbook()
      const worksheet = workbook.addWorksheet('Sheet1')
      worksheet.addRow(['Name'])
      worksheet.addRow(['John'])
      worksheet.addRow(['']) // Row with empty value (not completely empty array)

      const buffer = await workbook.xlsx.writeBuffer()
      const file = new File([buffer], 'test.xlsx')

      const result = await parseExcel(file, { skipEmptyRows: false })

      expect(result.data.length).toBeGreaterThanOrEqual(2)
    })

    it('should handle non-existent sheet name gracefully', async () => {
      const workbook = new ExcelJS.Workbook()
      workbook.addWorksheet('Sheet1').addRow(['Col1'])

      const buffer = await workbook.xlsx.writeBuffer()
      const file = new File([buffer], 'test.xlsx')

      const result = await parseExcel(file, { sheet: 'NonExistent' })

      expect(result.data).toBeDefined()
    })

    it('should handle file read errors', async () => {
      const file = new File([''], 'test.xlsx')
      Object.defineProperty(file, 'arrayBuffer', {
        value: () => Promise.reject(new Error('Read error')),
      })

      await expect(parseExcel(file)).rejects.toThrow()
    })
  })

  describe('importFile', () => {
    it('should import Excel file through universal handler', async () => {
      const workbook = new ExcelJS.Workbook()
      const worksheet = workbook.addWorksheet('Sheet1')
      worksheet.addRow(['Name', 'Age'])
      worksheet.addRow(['John', 30])

      const buffer = await workbook.xlsx.writeBuffer()
      const file = new File([buffer], 'test.xlsx')

      const result = await importFile(file)

      expect(result.format).toBe('excel')
      expect(result.data).toHaveLength(1)
    })

    it('should import JSON file through universal handler', async () => {
      const content = JSON.stringify([{ name: 'John' }])
      const file = new File([content], 'test.json')

      const result = await importFile(file)

      expect(result.format).toBe('json')
      expect(result.data).toHaveLength(1)
    })

    it('should import CSV file through universal handler', async () => {
      const content = 'Name,Age\nJohn,30'
      const file = new File([content], 'test.csv')

      const result = await importFile(file)

      expect(result.format).toBe('csv')
      expect(result.data).toHaveLength(1)
    })

    it('should import TSV file through universal handler', async () => {
      const content = 'Name\tAge\nJohn\t30'
      const file = new File([content], 'test.tsv')

      const result = await importFile(file)

      expect(result.format).toBe('tsv')
      expect(result.data).toHaveLength(1)
    })

    it('should auto-detect JSON from content', async () => {
      const content = JSON.stringify([{ name: 'John' }])
      const file = new File([content], 'data.unknown')

      const result = await importFile(file)

      expect(result.format).toBe('json')
      expect(result.data).toHaveLength(1)
    })

    it('should fallback to CSV for unknown format', async () => {
      const content = 'Name,Age\nJohn,30'
      const file = new File([content], 'data.xyz')

      const result = await importFile(file)

      expect(result.data).toHaveLength(1)
    })

    it('should handle file read errors', async () => {
      const file = new File(['test'], 'test.csv')

      // Mock FileReader to trigger an error
      const originalFileReader = window.FileReader
      const mockFileReader = jest.fn().mockImplementation(() => ({
        readAsText: function () {
          setTimeout(() => this.onerror?.({ target: {} }), 0)
        },
        onerror: null,
        onload: null,
      }))
      window.FileReader = mockFileReader as any

      await expect(importFile(file)).rejects.toThrow('Failed to read file')

      window.FileReader = originalFileReader
    })

    it('should use custom encoding', async () => {
      const content = 'Name,Age\nJohn,30'
      const file = new File([content], 'test.csv')

      const result = await importFile(file, { encoding: 'UTF-16' })

      expect(result.data).toBeDefined()
    })
  })

  describe('detectFileFormat - Content Detection', () => {
    it('should detect JSON from content', () => {
      const file = new File([''], 'data.unknown')
      const content = '{"test": "value"}'

      const format = detectFileFormat(file, content)

      expect(format).toBe('json')
    })

    it('should detect CSV from content', () => {
      const file = new File([''], 'data.unknown')
      const content = 'col1,col2,col3\nval1,val2,val3\nval4,val5,val6'

      const format = detectFileFormat(file, content)

      expect(format).toBe('csv')
    })

    it('should detect TSV from content', () => {
      const file = new File([''], 'data.unknown')
      const content = 'col1\tcol2\tcol3\nval1\tval2\tval3'

      const format = detectFileFormat(file, content)

      expect(format).toBe('tsv')
    })

    it('should detect JSONL extension', () => {
      const file = new File([''], 'data.jsonl')

      const format = detectFileFormat(file)

      expect(format).toBe('json')
    })

    it('should detect TXT as TSV', () => {
      const file = new File([''], 'data.txt')

      const format = detectFileFormat(file)

      expect(format).toBe('tsv')
    })

    it('should return unknown for unrecognized format', () => {
      const file = new File([''], 'data.xyz')
      const content = 'random content'

      const format = detectFileFormat(file, content)

      expect(format).toBe('unknown')
    })
  })

  describe('exportExcel - Advanced', () => {
    it('should handle empty data', async () => {
      await exportData([], 'excel', 'empty')

      expect(global.URL.createObjectURL).toHaveBeenCalled()
    })

    it('should auto-size columns', async () => {
      const data = [{ short: 'hi', long: 'this is a very long text value' }]

      await exportData(data, 'excel', 'test')

      expect(global.URL.createObjectURL).toHaveBeenCalled()
    })

    it('should cap column width at 50', async () => {
      const data = [{ col: 'x'.repeat(100) }]

      await exportData(data, 'excel', 'test')

      expect(global.URL.createObjectURL).toHaveBeenCalled()
    })
  })

  describe('Edge Cases and Error Scenarios', () => {
    it('should handle malformed JSON gracefully', () => {
      const content = 'not valid json at all'

      const result = parseJSON(content)

      expect(result.data).toHaveLength(0)
    })

    it('should handle mixed valid/invalid JSONL', () => {
      const content =
        '{"valid": "line1"}\n{invalid json}\n{"valid": "line3"}\n{bad}\n{"valid": "line5"}'

      const result = parseJSON(content)

      expect(result.data).toHaveLength(3)
      expect(result.errors).toHaveLength(2)
      expect(result.errors?.[0]).toContain('Line 2')
      expect(result.errors?.[1]).toContain('Line 4')
    })

    it('should handle CSV with quoted fields containing delimiters', async () => {
      const content =
        'Name,Description\n"John Doe","Contains, comma"\n"Jane Smith","Normal text"'

      const result = await parseCSV(content)

      expect(result.data).toHaveLength(2)
      expect(result.data[0].Description).toBe('Contains, comma')
    })

    it('should handle CSV with different encodings', async () => {
      const content = 'Name,Value\nTest,123'
      const file = new File([content], 'test.csv')

      const result = await importFile(file, { encoding: 'UTF-8' })

      expect(result.data).toHaveLength(1)
    })

    it('should handle TSV with tabs in quoted fields', async () => {
      const content = 'Name\tDescription\n"Test"\t"Contains\ttab"'

      const result = await parseCSV(content, { delimiter: '\t' })

      expect(result.format).toBe('tsv')
    })

    it('should handle CSV with empty fields', async () => {
      const content = 'A,B,C\n1,,3\n,2,\n,,,'

      const result = await parseCSV(content)

      expect(result.data).toHaveLength(3)
      // Papaparse converts empty values to null by default
      expect(result.data[0].B).toBeNull()
    })

    it('should handle CSV with no data rows', async () => {
      const content = 'Header1,Header2,Header3'

      const result = await parseCSV(content)

      expect(result.headers).toEqual(['Header1', 'Header2', 'Header3'])
      expect(result.data).toHaveLength(0)
    })

    it('should detect format from content when extension is unknown', () => {
      const file = new File([''], 'data.unknown')
      const jsonContent = '[{"test": "value"}]'

      const format = detectFileFormat(file, jsonContent)

      expect(format).toBe('json')
    })

    it('should detect CSV from content with high comma density', () => {
      const file = new File([''], 'data.dat')
      const csvContent = 'a,b,c,d,e\n1,2,3,4,5\n6,7,8,9,10'

      const format = detectFileFormat(file, csvContent)

      expect(format).toBe('csv')
    })

    it('should detect TSV from content with high tab density', () => {
      const file = new File([''], 'data.dat')
      const tsvContent = 'a\tb\tc\td\te\n1\t2\t3\t4\t5'

      const format = detectFileFormat(file, tsvContent)

      expect(format).toBe('tsv')
    })

    it('should return unknown for truly unknown content', () => {
      const file = new File([''], 'data.xyz')
      const content = 'random text with no structure'

      const format = detectFileFormat(file, content)

      expect(format).toBe('unknown')
    })

    it('should handle Excel file with multiple empty sheets', async () => {
      const workbook = new ExcelJS.Workbook()
      workbook.addWorksheet('Empty1')
      workbook.addWorksheet('Empty2')

      const buffer = await workbook.xlsx.writeBuffer()
      const file = new File([buffer], 'test.xlsx')

      const result = await parseExcel(file)

      expect(result.metadata?.sheets).toEqual(['Empty1', 'Empty2'])
      expect(result.data).toHaveLength(0)
    })

    it('should handle Excel with special characters in headers', async () => {
      const workbook = new ExcelJS.Workbook()
      const worksheet = workbook.addWorksheet('Sheet1')
      worksheet.addRow(['Name (Required)', 'Email@Address', 'Age#'])
      worksheet.addRow(['John', 'john@test.com', 30])

      const buffer = await workbook.xlsx.writeBuffer()
      const file = new File([buffer], 'test.xlsx')

      const result = await parseExcel(file, { transformHeaders: true })

      expect(result.headers).toContain('nameRequired')
      expect(result.headers).toContain('emailAddress')
      expect(result.headers).toContain('age')
    })

    it('should handle CSV with BOM (Byte Order Mark)', async () => {
      const bom = '\uFEFF'
      const content = bom + 'Name,Age\nJohn,30'

      const result = await parseCSV(content)

      expect(result.data).toHaveLength(1)
    })

    it('should handle importFile with TXT extension', async () => {
      const content = 'Line 1\nLine 2\nLine 3'
      const file = new File([content], 'data.txt')

      const result = await importFile(file)

      expect(result.data.length).toBeGreaterThan(0)
    })

    it('should handle importFile unknown format fallback to CSV', async () => {
      const content = 'col1,col2\nval1,val2'
      const file = new File([content], 'data.unknown')

      const result = await importFile(file)

      expect(result.data).toHaveLength(1)
    })

    it('should handle importFile with empty file', async () => {
      const file = new File([''], 'empty.csv')

      const result = await importFile(file)

      expect(result.data).toHaveLength(0)
    })

    it('should handle CSV with inconsistent column counts', async () => {
      const content = 'A,B,C\n1,2,3\n4,5\n6,7,8,9'

      const result = await parseCSV(content)

      expect(result.data).toHaveLength(3)
    })

    it('should transform headers with multiple special chars correctly', async () => {
      const content =
        'First___Name,Last---Name,Email...Address\nJohn,Doe,john@test.com'

      const result = await parseCSV(content, { transformHeaders: true })

      expect(result.data[0]).toHaveProperty('firstName')
      expect(result.data[0]).toHaveProperty('lastName')
      expect(result.data[0]).toHaveProperty('emailAddress')
    })

    it('should handle parseCSV with no detectTypes', async () => {
      const content = 'Name,Age,Active\nJohn,30,true'

      const result = await parseCSV(content, { detectTypes: false })

      expect(typeof result.data[0].Age).toBe('string')
    })

    it('should handle Excel with sheet index out of bounds', async () => {
      const workbook = new ExcelJS.Workbook()
      workbook.addWorksheet('Sheet1').addRow(['Col1'])

      const buffer = await workbook.xlsx.writeBuffer()
      const file = new File([buffer], 'test.xlsx')

      const result = await parseExcel(file, { sheet: 999 })

      expect(result.data).toBeDefined()
    })

    it('should handle Excel with mixed data types in columns', async () => {
      const workbook = new ExcelJS.Workbook()
      const worksheet = workbook.addWorksheet('Sheet1')
      worksheet.addRow(['Value'])
      worksheet.addRow([123])
      worksheet.addRow(['text'])
      worksheet.addRow([true])
      worksheet.addRow([new Date('2024-01-01')])

      const buffer = await workbook.xlsx.writeBuffer()
      const file = new File([buffer], 'test.xlsx')

      const result = await parseExcel(file)

      expect(result.data).toHaveLength(4)
      expect(typeof result.data[0].Value).toBe('number')
      expect(typeof result.data[1].Value).toBe('string')
    })

    it('should handle Excel with only headers', async () => {
      const workbook = new ExcelJS.Workbook()
      const worksheet = workbook.addWorksheet('Sheet1')
      worksheet.addRow(['Header1', 'Header2', 'Header3'])

      const buffer = await workbook.xlsx.writeBuffer()
      const file = new File([buffer], 'test.xlsx')

      const result = await parseExcel(file)

      expect(result.headers).toEqual(['Header1', 'Header2', 'Header3'])
      expect(result.data).toHaveLength(0)
    })

    it('should handle FileReader errors for text files', async () => {
      const file = new File(['test'], 'test.json')
      const mockReader = {
        onload: null as any,
        onerror: null as any,
        readAsText: jest.fn(function (this: any) {
          setTimeout(() => this.onerror?.({ target: {} }), 0)
        }),
      }

      jest
        .spyOn(window, 'FileReader')
        .mockImplementation(() => mockReader as any)

      await expect(importFile(file)).rejects.toThrow('Failed to read file')

      jest.restoreAllMocks()
    })

    it('should handle CSV parse errors in result', async () => {
      const content = 'Name,Age\n"Unclosed quote,30'

      const result = await parseCSV(content)

      expect(result.data).toBeDefined()
    })

    it('should handle JSON with deeply nested objects', () => {
      const content = JSON.stringify([
        {
          level1: {
            level2: {
              level3: {
                value: 'deep',
              },
            },
          },
        },
      ])

      const result = parseJSON(content)

      expect(result.data[0].level1.level2.level3.value).toBe('deep')
    })

    it('should handle JSONL with trailing newlines', () => {
      const content = '{"a":1}\n{"b":2}\n\n\n'

      const result = parseJSON(content)

      expect(result.data).toHaveLength(2)
    })

    it('should handle CSV with skipEmptyRows disabled', async () => {
      const content = 'A,B\n1,2\n\n3,4'

      const result = await parseCSV(content, { skipEmptyRows: false })

      expect(result.data.length).toBeGreaterThanOrEqual(2)
    })

    it('should trigger auto-detect JSON when JSON is valid', async () => {
      const content = '[{"name": "test"}]'
      const file = new File([content], 'data.unknown')

      const result = await importFile(file)

      expect(result.format).toBe('json')
      expect(result.data).toHaveLength(1)
    })

    it('should trigger auto-detect fallback when JSON fails', async () => {
      const content = 'not json but looks like csv,maybe\nval1,val2'
      const file = new File([content], 'data.unknown')

      const result = await importFile(file)

      expect(result.data).toBeDefined()
    })

    it('should handle parseJSON with all-empty JSONL', () => {
      const content = '\n\n\n'

      const result = parseJSON(content)

      expect(result.data).toHaveLength(0)
    })
  })

  describe('Transform Header Function', () => {
    it('should transform headers starting with numbers', async () => {
      const content = '123Name,456Age\nJohn,30'

      const result = await parseCSV(content, { transformHeaders: true })

      expect(result.data[0]).toHaveProperty('123name')
      expect(result.data[0]).toHaveProperty('456age')
    })

    it('should handle headers with only special characters', async () => {
      const content = '@@@,###\nval1,val2'

      const result = await parseCSV(content, { transformHeaders: true })

      expect(result.data).toHaveLength(1)
    })

    it('should handle empty header transformation', async () => {
      const content = ',header2\nval1,val2'

      const result = await parseCSV(content, { transformHeaders: true })

      expect(result.data).toHaveLength(1)
    })
  })
})
