/**
 * The model a picker starts on when the user (or a saved config) has not
 * chosen one.
 *
 * ONE constant, because this used to be a bare `'gpt-4o'` string literal
 * repeated at a dozen call sites in the evaluation builder alone — so the
 * catalog moved on and the pickers silently did not. Anything that needs a
 * "start here" model imports this instead of hardcoding an id.
 *
 * Requirements for whatever id sits here: it must be an ACTIVE, OFFICIAL
 * catalog row (services/shared/seeds/llm_models.yaml). A deactivated or BYOM
 * id would leave every picker preselected on a model the backend refuses.
 */
export const DEFAULT_MODEL_ID = 'gpt-5.4-mini'
