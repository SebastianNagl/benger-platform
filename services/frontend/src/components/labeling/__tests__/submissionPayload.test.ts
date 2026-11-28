import { buildSubmissionPayload } from '../submissionPayload'

describe('buildSubmissionPayload', () => {
  const timing = { activeMs: 1200, focusedMs: 900, tabSwitches: 2 }

  it('carries every research field of a submission', () => {
    expect(
      buildSubmissionPayload({
        result: [],
        leadTimeSeconds: 42,
        timing,
        instructionVariant: 'v1',
      }),
    ).toEqual({
      result: [],
      was_cancelled: false,
      lead_time: 42,
      active_duration_ms: 1200,
      focused_duration_ms: 900,
      tab_switches: 2,
      instruction_variant: 'v1',
    })
  })

  it('leaves the variant out when none was shown', () => {
    const payload = buildSubmissionPayload({
      result: [],
      leadTimeSeconds: 0,
      timing,
      instructionVariant: null,
    })
    expect(payload.instruction_variant).toBeUndefined()
  })
})
