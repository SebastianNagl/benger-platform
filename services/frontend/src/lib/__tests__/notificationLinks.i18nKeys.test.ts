/**
 * Every string the "new grading" notifications render exists in both locales.
 *
 * Component tests mock `t`, so a mistyped key passes them and shows the raw
 * key on a real page. This checks the settings labels (read straight from the
 * settings page source) and the bell/notification-page content per type. The
 * content may only use {project_title}: getTranslatedNotification falls back
 * to the raw DB text when a placeholder stays unresolved.
 */
import { EVALUATION_RECEIVED_TYPES } from '@/lib/notificationLinks'
import * as fs from 'fs'
import * as path from 'path'

const read = (relative: string) =>
  fs.readFileSync(path.resolve(__dirname, relative), 'utf8')

const locale = (lang: string) =>
  JSON.parse(read(`../../locales/${lang}/common.json`))

const lookup = (tree: any, key: string) =>
  key
    .split('.')
    .reduce((node, part) => (node == null ? node : node[part]), tree)

const settingsPageKeys = Array.from(
  read('../../app/settings/notifications/page.tsx').matchAll(
    /'(settings\.notifications\.types\.evaluationReceived\w+)'/g,
  ),
  (match) => match[1],
)

describe.each(['de', 'en'])('%s locale', (lang) => {
  const tree = locale(lang)

  it('has every evaluation-received label the settings page uses', () => {
    // Three types, each with a name and a description.
    expect(settingsPageKeys).toHaveLength(6)
    for (const key of settingsPageKeys) {
      expect(typeof lookup(tree, key)).toBe('string')
    }
  })

  it.each(EVALUATION_RECEIVED_TYPES)(
    'has notification content for %s using only {project_title}',
    (type) => {
      for (const part of ['title', 'message']) {
        const text = lookup(tree, `notifications.content.${type}.${part}`)
        expect(typeof text).toBe('string')
        const placeholders: string[] = text.match(/\{\w+\}/g) ?? []
        expect(placeholders.every((p) => p === '{project_title}')).toBe(true)
      }
    },
  )
})
