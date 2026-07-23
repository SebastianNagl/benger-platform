import { redirect } from 'next/navigation'

/**
 * Custom-model (BYOM) management moved to the catalog page: /models hosts
 * the official catalog AND the community section (register, edit/delete,
 * per-user keys) in one place. This route survives only as a redirect so
 * old bookmarks, in-app "configure key" hints, and external links keep
 * working.
 */
export default function ModelSettingsRedirect() {
  redirect('/models')
}
