/**
 * Project questionnaires (overlay contract, core 2.91): the platform owns the
 * model, the settings, the renderer and the participant moments; an overlay
 * shows a questionnaire on its own surfaces with these components.
 *
 * - `QuestionnairePrompt` after an action: `trigger="after_submit"` with
 *   `subject={{ annotation_id }}` once a submission is final, or
 *   `trigger="korrektur"` with `subject={{ task_evaluation_id }}` once a
 *   grader saved a Korrektur (the answers are the grader's).
 * - `BeforeTaskQuestionnaireGate` around a task view that includes its exam
 *   timer: the task and the timer mount only once the before-task
 *   questionnaire is answered or skipped, so it never counts toward the time.
 */

export {
  BeforeTaskQuestionnaireGate,
  BeforeTaskQuestionnaireScreen,
  useBeforeTaskQuestionnaire,
  type BeforeTaskPhase,
} from './BeforeTaskQuestionnaire'
export { QuestionnaireDialog } from './QuestionnaireDialog'
export { QuestionnaireForm } from './QuestionnaireForm'
export {
  QuestionnairePrompt,
  type QuestionnaireOutcome,
} from './QuestionnairePrompt'
export { QuestionnairesSettings } from './QuestionnairesSettings'
