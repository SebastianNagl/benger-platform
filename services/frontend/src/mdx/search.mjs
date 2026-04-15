import { slugifyWithCounter } from '@sindresorhus/slugify'
import { toString } from 'mdast-util-to-string'
import { remark } from 'remark'
import remarkMdx from 'remark-mdx'
import { createLoader } from 'simple-functional-loader'
import { filter } from 'unist-util-filter'
import { SKIP, visit } from 'unist-util-visit'
import * as url from 'url'

const __filename = url.fileURLToPath(import.meta.url)
const processor = remark().use(remarkMdx).use(extractSections)
const slugify = slugifyWithCounter()

// Define all available pages for search
const allPages = [
  // Main BenGER pages (actual functional pages)
  {
    url: '/',
    title: 'Home',
    description: 'BenGER - Benchmark für Deutsches Recht',
    category: 'BenGER',
  },
  {
    url: '/about',
    title: 'About',
    description: 'Learn about BenGER and its mission for legal language models',
    category: 'BenGER',
  },
  {
    url: '/architektur',
    title: 'Architektur',
    description: 'Technical architecture and design of the BenGER project',
    category: 'BenGER',
  },
  {
    url: '/dashboard',
    title: 'Dashboard',
    description: 'Your personal dashboard and overview',
    category: 'BenGER',
  },

  // Legal pages
  {
    url: '/about/imprint',
    title: 'Impressum',
    description: 'Legal imprint and contact information',
    category: 'BenGER',
  },
  {
    url: '/about/data-protection',
    title: 'Datenschutzerklärung',
    description: 'Privacy policy and data protection information',
    category: 'BenGER',
  },

  // Tasks & Data (actual functional pages)
  {
    url: '/tasks',
    title: 'Tasks',
    description: 'Browse and manage annotation tasks',
    category: 'Tasks & Data',
  },
  {
    url: '/data',
    title: 'Data Management',
    description: 'Manage uploads, view datasets, and generate synthetic data',
    category: 'Tasks & Data',
  },
  {
    url: '/evaluation',
    title: 'Evaluation',
    description: 'View evaluation results and run model evaluations',
    category: 'Tasks & Data',
  },

  // Administration (role-based)
  {
    url: '/admin/users',
    title: 'User Management',
    description: 'Manage users, roles, and permissions',
    category: 'Administration',
  },
]

function isObjectExpression(node) {
  return (
    node.type === 'mdxTextExpression' &&
    node.data?.estree?.body?.[0]?.expression?.type === 'ObjectExpression'
  )
}

function excludeObjectExpressions(tree) {
  return filter(tree, (node) => !isObjectExpression(node))
}

function extractSections() {
  return (tree, { sections }) => {
    slugify.reset()

    visit(tree, (node) => {
      if (node.type === 'heading' || node.type === 'paragraph') {
        let content = toString(excludeObjectExpressions(node))
        if (node.type === 'heading' && node.depth <= 2) {
          let hash = node.depth === 1 ? null : slugify(content)
          sections.push([content, hash, []])
        } else {
          sections.at(-1)?.[2].push(content)
        }
        return SKIP
      }
    })
  }
}

export default function Search(nextConfig = {}) {
  let cache = new Map()

  return Object.assign({}, nextConfig, {
    webpack(config, options) {
      config.module.rules.push({
        test: __filename,
        use: [
          createLoader(function () {
            // Temporarily disable all MDX file processing to isolate the issue

            let mdxData = []

            // When this file is imported within the application
            // the following module is loaded:
            return `
              import FlexSearch from 'flexsearch'

              let sectionIndex = new FlexSearch.Document({
                tokenize: 'full',
                document: {
                  id: 'url',
                  index: ['content', 'title', 'description', 'category'],
                  store: ['title', 'pageTitle', 'description', 'category'],
                },
                context: {
                  resolution: 9,
                  depth: 2,
                  bidirectional: true
                }
              })

              // Add all predefined pages to search index
              let allPages = ${JSON.stringify(allPages)}
              for (let page of allPages) {
                sectionIndex.add({
                  url: page.url,
                  title: page.title,
                  content: [page.title, page.description, page.category].join(' '),
                  description: page.description,
                  category: page.category,
                  pageTitle: page.title,
                })
              }

              // Temporarily disable MDX content indexing to isolate the error
              // TODO: Re-enable after fixing the file scanning issue
              /*
              // Add MDX content sections
              let mdxData = ${JSON.stringify(mdxData)}
              
              // Define which pages we want to include MDX content for (only real BenGER content)
              let allowedMdxPages = ['/', '/about', '/architektur', '/about/imprint', '/about/data-protection']
              
              for (let { url, sections } of mdxData) {
                // Only process MDX content for pages we want to keep
                if (url && allowedMdxPages.includes(url)) {
                  for (let [title, hash, content] of sections) {
                    // Ensure title exists and is a string
                    if (!title || typeof title !== 'string') continue
                    
                    let fullUrl = url + (hash && typeof hash === 'string' ? ('#' + hash) : '')
                    sectionIndex.add({
                      url: fullUrl,
                      title,
                      content: [title, ...(Array.isArray(content) ? content : [])].join('\\n'),
                      pageTitle: hash && sections[0] ? sections[0][0] : undefined,
                      category: 'BenGER'
                    })
                  }
                }
              }
              */

              export function search(query, options = {}) {
                let result = sectionIndex.search(query, {
                  ...options,
                  enrich: true,
                })
                if (result.length === 0) {
                  return []
                }
                return result[0].result.map((item) => ({
                  url: item.id,
                  title: item.doc.title,
                  pageTitle: item.doc.pageTitle,
                  description: item.doc.description,
                  category: item.doc.category,
                }))
              }

              export { allPages }
            `
          }),
        ],
      })

      if (typeof nextConfig.webpack === 'function') {
        return nextConfig.webpack(config, options)
      }

      return config
    },
  })
}
