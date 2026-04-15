/**
 * JsonViewer component for displaying JSON data in a tree-like structure
 */

import { ChevronDownIcon, ChevronRightIcon } from '@heroicons/react/24/outline'
import { useState } from 'react'

interface JsonViewerProps {
  data: any
  expanded?: boolean
  depth?: number
  maxDepth?: number
}

export function JsonViewer({
  data,
  expanded = false,
  depth = 0,
  maxDepth = 10,
}: JsonViewerProps) {
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(
    new Set(expanded ? ['root'] : [])
  )

  const toggleNode = (path: string) => {
    const newExpanded = new Set(expandedNodes)
    if (newExpanded.has(path)) {
      newExpanded.delete(path)
    } else {
      newExpanded.add(path)
    }
    setExpandedNodes(newExpanded)
  }

  const renderValue = (value: any, path: string = 'root'): JSX.Element => {
    // Handle null/undefined
    if (value === null) {
      return <span className="text-orange-600">null</span>
    }
    if (value === undefined) {
      return <span className="text-gray-500">undefined</span>
    }

    // Handle primitives
    if (typeof value === 'string') {
      return <span className="text-green-600">"{value}"</span>
    }
    if (typeof value === 'number') {
      return <span className="text-blue-600">{value}</span>
    }
    if (typeof value === 'boolean') {
      return <span className="text-purple-600">{value.toString()}</span>
    }

    // Handle arrays
    if (Array.isArray(value)) {
      const isExpanded = expandedNodes.has(path) || (expanded && depth < 2)

      if (value.length === 0) {
        return <span className="text-gray-600">[]</span>
      }

      // Simple array of primitives - inline display
      if (value.every((item) => typeof item !== 'object' || item === null)) {
        return (
          <span className="text-gray-600">
            [
            {value.map((item, i) => (
              <span key={i}>
                {i > 0 && ', '}
                {renderValue(item, `${path}[${i}]`)}
              </span>
            ))}
            ]
          </span>
        )
      }

      // Complex array - expandable
      return (
        <span>
          <button
            onClick={() => toggleNode(path)}
            className="text-gray-600 hover:text-gray-800 focus:outline-none"
          >
            {isExpanded ? (
              <ChevronDownIcon className="inline h-3 w-3" />
            ) : (
              <ChevronRightIcon className="inline h-3 w-3" />
            )}
            <span className="ml-1">Array[{value.length}]</span>
          </button>
          {isExpanded && depth < maxDepth && (
            <div className="ml-4 mt-1">
              {value.map((item, i) => (
                <div key={i} className="my-1">
                  <span className="mr-2 text-gray-500">{i}:</span>
                  {renderValue(item, `${path}[${i}]`)}
                </div>
              ))}
            </div>
          )}
        </span>
      )
    }

    // Handle objects
    if (typeof value === 'object') {
      const keys = Object.keys(value)
      const isExpanded = expandedNodes.has(path) || (expanded && depth < 2)

      if (keys.length === 0) {
        return <span className="text-gray-600">{'{}'}</span>
      }

      return (
        <span>
          <button
            onClick={() => toggleNode(path)}
            className="text-gray-600 hover:text-gray-800 focus:outline-none"
          >
            {isExpanded ? (
              <ChevronDownIcon className="inline h-3 w-3" />
            ) : (
              <ChevronRightIcon className="inline h-3 w-3" />
            )}
            <span className="ml-1">Object{`{${keys.length}}`}</span>
          </button>
          {isExpanded && depth < maxDepth && (
            <div className="ml-4 mt-1">
              {keys.map((key) => (
                <div key={key} className="my-1">
                  <span className="font-medium text-gray-700">{key}:</span>{' '}
                  {renderValue(value[key], `${path}.${key}`)}
                </div>
              ))}
            </div>
          )}
        </span>
      )
    }

    // Fallback for unknown types
    return <span className="text-gray-500">{String(value)}</span>
  }

  return (
    <div className="max-h-[600px] overflow-auto rounded-lg bg-gray-50 p-4 font-mono text-sm dark:bg-gray-900">
      {renderValue(data)}
    </div>
  )
}
