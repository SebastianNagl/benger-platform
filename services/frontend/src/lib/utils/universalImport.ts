/**
 * Universal import handler for multiple file formats
 * Issue #220: Support CSV, Excel, JSON, and more without rigid structure
 */

import * as ExcelJS from 'exceljs'
import * as Papa from 'papaparse'

export interface ImportResult {
  data: any[]
  format: 'json' | 'csv' | 'excel' | 'tsv' | 'unknown'
  headers?: string[]
  errors?: string[]
  metadata?: {
    totalRows: number
    totalColumns?: number
    sheets?: string[]
    encoding?: string
  }
}

export interface ImportOptions {
  sheet?: string | number // For Excel files
  delimiter?: string // For CSV/TSV
  encoding?: string
  skipEmptyRows?: boolean
  transformHeaders?: boolean // Convert headers to camelCase
  detectTypes?: boolean // Try to detect number/boolean types
}

/**
 * Detect file format from extension or content
 */
export function detectFileFormat(
  file: File,
  content?: string
): 'json' | 'csv' | 'excel' | 'tsv' | 'unknown' {
  const extension = file.name.split('.').pop()?.toLowerCase()

  // Check by extension first
  switch (extension) {
    case 'json':
    case 'jsonl':
      return 'json'
    case 'csv':
      return 'csv'
    case 'tsv':
    case 'txt':
      return 'tsv'
    case 'xlsx':
    case 'xls':
      return 'excel'
  }

  // Try to detect from content
  if (content) {
    // Check if JSON
    try {
      JSON.parse(content)
      return 'json'
    } catch {}

    // Check if likely CSV/TSV
    const lines = content.split('\n').slice(0, 5)
    const avgCommas =
      lines.reduce((sum, line) => sum + (line.match(/,/g) || []).length, 0) /
      lines.length
    const avgTabs =
      lines.reduce((sum, line) => sum + (line.match(/\t/g) || []).length, 0) /
      lines.length

    if (avgTabs > avgCommas && avgTabs > 0.5) return 'tsv'
    if (avgCommas > 0.5) return 'csv'
  }

  return 'unknown'
}

/**
 * Parse JSON file with support for JSONL and nested structures
 */
export function parseJSON(content: string): ImportResult {
  const errors: string[] = []
  let data: any[] = []

  try {
    // Try standard JSON first
    const parsed = JSON.parse(content)
    data = Array.isArray(parsed) ? parsed : [parsed]
  } catch {
    // Try JSONL format (one JSON object per line)
    const lines = content.trim().split('\n')
    for (let i = 0; i < lines.length; i++) {
      try {
        if (lines[i].trim()) {
          data.push(JSON.parse(lines[i]))
        }
      } catch (e) {
        errors.push(`Line ${i + 1}: Invalid JSON`)
      }
    }
  }

  return {
    data,
    format: 'json',
    errors: errors.length > 0 ? errors : undefined,
    metadata: {
      totalRows: data.length,
    },
  }
}

/**
 * Parse CSV/TSV with intelligent type detection
 */
export async function parseCSV(
  content: string,
  options: ImportOptions = {}
): Promise<ImportResult> {
  return new Promise((resolve) => {
    Papa.parse(content, {
      delimiter: options.delimiter,
      header: true,
      skipEmptyLines: options.skipEmptyRows ?? true,
      dynamicTyping: options.detectTypes ?? true,
      complete: (results) => {
        const data = results.data as any[]
        const headers = results.meta.fields || []

        // Transform headers if requested
        if (options.transformHeaders && headers.length > 0) {
          data.forEach((row) => {
            const transformed: any = {}
            Object.entries(row).forEach(([key, value]) => {
              const newKey = transformHeaderName(key)
              transformed[newKey] = value
            })
            Object.assign(row, transformed)
          })
        }

        resolve({
          data,
          format: options.delimiter === '\t' ? 'tsv' : 'csv',
          headers,
          errors:
            results.errors.length > 0
              ? results.errors.map((e) => `Row ${e.row}: ${e.message}`)
              : undefined,
          metadata: {
            totalRows: data.length,
            totalColumns: headers.length,
          },
        })
      },
    })
  })
}

/**
 * Parse Excel files with sheet selection using ExcelJS
 * Updated to use ExcelJS to address security vulnerabilities (Issue #369)
 */
export async function parseExcel(
  file: File,
  options: ImportOptions = {}
): Promise<ImportResult> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()

    reader.onload = async (e) => {
      try {
        const data = e.target?.result as ArrayBuffer
        const workbook = new ExcelJS.Workbook()
        await workbook.xlsx.load(data)

        // Get sheet names
        const sheetNames = workbook.worksheets.map((ws) => ws.name)

        // Select sheet
        let worksheet: ExcelJS.Worksheet
        if (typeof options.sheet === 'number') {
          worksheet =
            workbook.worksheets[options.sheet] || workbook.worksheets[0]
        } else if (options.sheet) {
          worksheet =
            workbook.getWorksheet(options.sheet) || workbook.worksheets[0]
        } else {
          worksheet = workbook.worksheets[0]
        }

        // Convert worksheet to JSON
        const jsonData: any[] = []
        let headers: string[] = []

        worksheet.eachRow((row, rowNumber) => {
          if (rowNumber === 1) {
            // First row as headers
            const values = Array.isArray(row.values) ? row.values : []
            headers = values.slice(1) as string[] // slice(1) because ExcelJS uses 1-based indexing
          } else {
            const rowData: any = {}
            const values = Array.isArray(row.values) ? row.values : []
            values.slice(1).forEach((value, index) => {
              const header = headers[index] || `Column${index + 1}`
              // Handle different value types
              if (value instanceof Date) {
                rowData[header] = value.toISOString()
              } else if (
                typeof value === 'object' &&
                value !== null &&
                'result' in value
              ) {
                // Handle formula results
                rowData[header] = value.result
              } else {
                rowData[header] = value
              }
            })

            // Add row based on skipEmptyRows option
            const isEmptyRow =
              Object.keys(rowData).length === 0 ||
              Object.values(rowData).every(
                (v) => v === undefined || v === null || v === ''
              )
            const shouldAddRow = options.skipEmptyRows === false || !isEmptyRow

            if (shouldAddRow) {
              jsonData.push(rowData)
            }
          }
        })

        // Transform headers if requested
        if (options.transformHeaders && jsonData.length > 0) {
          jsonData.forEach((row) => {
            const transformed: any = {}
            Object.entries(row).forEach(([key, value]) => {
              const newKey = transformHeaderName(key)
              transformed[newKey] = value
            })
            Object.assign(row, transformed)
          })
          // Update headers array too
          headers = headers.map((h) => transformHeaderName(h))
        }

        resolve({
          data: jsonData,
          format: 'excel',
          headers,
          metadata: {
            totalRows: jsonData.length,
            totalColumns: headers.length,
            sheets: sheetNames,
          },
        })
      } catch (error) {
        reject(new Error(`Failed to parse Excel file: ${error}`))
      }
    }

    reader.onerror = () => reject(new Error('Failed to read file'))
    reader.readAsArrayBuffer(file)
  })
}

/**
 * Universal import function that handles any file type
 */
export async function importFile(
  file: File,
  options: ImportOptions = {}
): Promise<ImportResult> {
  const format = detectFileFormat(file)

  if (format === 'excel') {
    return parseExcel(file, options)
  }

  // Read file as text for other formats
  return new Promise((resolve, reject) => {
    const reader = new FileReader()

    reader.onload = async (e) => {
      const content = e.target?.result as string

      try {
        switch (format) {
          case 'json':
            resolve(parseJSON(content))
            break
          case 'csv':
            resolve(await parseCSV(content, { ...options, delimiter: ',' }))
            break
          case 'tsv':
            resolve(await parseCSV(content, { ...options, delimiter: '\t' }))
            break
          default:
            // Try to auto-detect
            const jsonResult = parseJSON(content)
            if (jsonResult.data.length > 0 && !jsonResult.errors) {
              resolve(jsonResult)
            } else {
              // Fallback to CSV
              resolve(await parseCSV(content, options))
            }
        }
      } catch (error) {
        reject(new Error(`Failed to parse file: ${error}`))
      }
    }

    reader.onerror = () => reject(new Error('Failed to read file'))
    reader.readAsText(file, options.encoding || 'UTF-8')
  })
}

/**
 * Transform header names to camelCase
 */
function transformHeaderName(header: string): string {
  return header
    .toLowerCase()
    .replace(/[^a-zA-Z0-9]+(.)/g, (_, chr) => chr.toUpperCase())
    .replace(/[^a-zA-Z0-9]+$/g, '') // Remove trailing special characters
    .replace(/^./, (chr) => chr.toLowerCase())
}

/**
 * Export data to various formats
 * Updated to be async to support ExcelJS (Issue #369)
 */
export async function exportData(
  data: any[],
  format: 'json' | 'csv' | 'excel',
  filename: string
): Promise<void> {
  switch (format) {
    case 'json':
      exportJSON(data, filename)
      break
    case 'csv':
      exportCSV(data, filename)
      break
    case 'excel':
      await exportExcel(data, filename)
      break
  }
}

function exportJSON(data: any[], filename: string): void {
  const json = JSON.stringify(data, null, 2)
  const blob = new Blob([json], { type: 'application/json' })
  downloadBlob(blob, `${filename}.json`)
}

function exportCSV(data: any[], filename: string): void {
  const csv = Papa.unparse(data)
  const blob = new Blob([csv], { type: 'text/csv' })
  downloadBlob(blob, `${filename}.csv`)
}

async function exportExcel(data: any[], filename: string): Promise<void> {
  // Create a new workbook using ExcelJS
  const workbook = new ExcelJS.Workbook()
  const worksheet = workbook.addWorksheet('Data')

  // Add headers if data is not empty
  if (data.length > 0) {
    const headers = Object.keys(data[0])
    worksheet.addRow(headers)

    // Add data rows
    data.forEach((item) => {
      const row = headers.map((header) => item[header])
      worksheet.addRow(row)
    })

    // Auto-fit columns
    worksheet.columns.forEach((column) => {
      let maxLength = 0
      column.eachCell?.({ includeEmpty: false }, (cell) => {
        const cellLength = cell.value ? cell.value.toString().length : 0
        if (cellLength > maxLength) {
          maxLength = cellLength
        }
      })
      column.width = Math.min(maxLength + 2, 50) // Cap at 50 characters
    })
  }

  // Generate buffer and download
  const buffer = await workbook.xlsx.writeBuffer()
  const blob = new Blob([buffer], {
    type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  })
  downloadBlob(blob, `${filename}.xlsx`)
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}
