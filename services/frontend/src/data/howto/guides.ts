/**
 * Platform how-to guides (open-core), one module per topic under ./guides.
 * Registered into the how-to registry at import time so both the /how-to
 * page and the nav-bar search see them. Extended-edition guides (student
 * surface) are registered by the extended package under its own source.
 *
 * Writing guidelines: question-style titles, the short answer first, steps
 * in the words of the UI (German labels as rendered), then what typically
 * goes wrong. Inline `code`, **bold** and [label](/path) are rendered.
 */

import { registerHowToGuides, type HowToGuide } from '@/lib/howto'

import { ANNOTATION_GUIDES } from './guides/annotation'
import { DATA_GUIDES } from './guides/data'
import { EVALUATION_GUIDES } from './guides/evaluation'
import { GENERATION_GUIDES } from './guides/generation'
import { INTEGRATION_GUIDES } from './guides/integrations'
import { ORGANIZATION_GUIDES } from './guides/organizations'
import { PROJECT_GUIDES } from './guides/projects'
import { START_GUIDES } from './guides/start'
import { TROUBLESHOOTING_GUIDES } from './guides/troubleshooting'

export const PLATFORM_HOWTO_GUIDES: HowToGuide[] = [
  ...START_GUIDES,
  ...ORGANIZATION_GUIDES,
  ...PROJECT_GUIDES,
  ...DATA_GUIDES,
  ...ANNOTATION_GUIDES,
  ...GENERATION_GUIDES,
  ...EVALUATION_GUIDES,
  ...INTEGRATION_GUIDES,
  ...TROUBLESHOOTING_GUIDES,
]

registerHowToGuides('platform', PLATFORM_HOWTO_GUIDES)
