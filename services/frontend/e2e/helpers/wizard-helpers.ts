/**
 * Shared helpers for the project-creation wizard.
 *
 * The wizard is a dynamic feature-toggle flow: every feature is OFF by
 * default and the wizard renders only the steps the user opts into. Specs
 * that walk the wizard must opt in explicitly via {@link enableWizardFeatures}
 * and submit via {@link clickSubmitFromAnyStep}, which knows how to walk
 * past whatever extra steps the enabled features inserted.
 *
 * Keys mirror WizardFeatures in:
 *   services/frontend/src/components/projects/wizard/types.ts:53
 */

import type { Page } from '@playwright/test'

export type WizardFeatureKey =
  | 'annotation'
  | 'dataImport'
  | 'llmGeneration'
  | 'evaluation'

/**
 * Tick the named feature checkboxes on the wizard's projectInfo step.
 * Must be called BEFORE the first click on the Next button — feature
 * toggles only render on step 1 and they determine the step list.
 */
export async function enableWizardFeatures(
  page: Page,
  features: WizardFeatureKey[]
): Promise<void> {
  for (const key of features) {
    await page
      .locator(`[data-testid="wizard-feature-${key}"] input[type="checkbox"]`)
      .check()
  }
  console.log(`[enableWizardFeatures] enabled: ${features.join(', ')}`)
}

/**
 * Walk the wizard from the current step to the final Submit step,
 * clicking Next as needed. Asserts that each Next click strictly
 * advances the step indicator — if the wizard stalls, throws within
 * ~5 s with a useful message instead of silently looping.
 *
 * Requires the source-side `data-testid="project-create-step-indicator"`
 * with a `data-step="N"` attribute (added in ProjectCreationWizard.tsx).
 */
export async function clickSubmitFromAnyStep(page: Page): Promise<void> {
  const submit = page.locator('[data-testid="project-create-submit-button"]')
  const next = page.locator('[data-testid="project-create-next-button"]')
  const indicatorSel = '[data-testid="project-create-step-indicator"]'
  const indicator = page.locator(indicatorSel)

  const readStep = async (): Promise<number> => {
    const raw = await indicator.getAttribute('data-step').catch(() => null)
    return parseInt(raw ?? '0', 10)
  }

  let prev = await readStep()
  if (prev === 0) {
    throw new Error(
      `clickSubmitFromAnyStep called but no step indicator found at ${page.url()}`
    )
  }

  // 8 iterations is enough for any plausible feature combination
  // (projectInfo + dataImport + 2 annotation + 2 generation + evaluation
  // + settings = 8 steps max).
  for (let i = 0; i < 8; i++) {
    if (await submit.isVisible({ timeout: 500 }).catch(() => false)) {
      await submit.click()
      return
    }
    await next.click()
    try {
      await page.waitForFunction(
        ({ prev: prevStep, sel }: { prev: number; sel: string }) => {
          const raw = document.querySelector(sel)?.getAttribute('data-step')
          return parseInt(raw ?? '0', 10) > prevStep
        },
        { prev, sel: indicatorSel },
        { timeout: 5000 }
      )
    } catch {
      throw new Error(
        `Wizard step did not advance past ${prev} after Next click ` +
          `at ${page.url()} — likely a wizard regression`
      )
    }
    prev = await readStep()
  }
  throw new Error(
    `Submit button never appeared after 8 Next clicks; stuck at step ${prev}`
  )
}
