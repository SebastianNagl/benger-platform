/**
 * Starting points for each moment's questionnaire. Each is label-config XML
 * that passes the server's questionnaire validation; the texts are the
 * questionnaire's content (what a participant reads), not interface copy,
 * and the author edits them freely. The menu names are catalog keys
 * (`questionnaires.templates.<id>`).
 */

import type { QuestionnaireTrigger } from '@/lib/api/questionnaires'

export interface QuestionnaireTemplate {
  id: string
  xml: string
}

const CONFIDENCE_DIFFICULTY = `<View>
  <Header value="Post-Annotation Feedback"/>
  <Rating name="confidence" toName="confidence" maxRating="5" required="true" label="How confident are you in your annotation?"/>
  <Rating name="difficulty" toName="difficulty" maxRating="5" required="true" label="How difficult was this task?"/>
</View>`

const EXTENDED_FEEDBACK = `<View>
  <Header value="Post-Annotation Feedback"/>
  <Rating name="confidence" toName="confidence" maxRating="5" required="true" label="How confident are you in your annotation?"/>
  <Rating name="difficulty" toName="difficulty" maxRating="5" required="true" label="How difficult was this task?"/>
  <Choices name="guideline_clarity" toName="guideline_clarity" choice="single" layout="horizontal" required="true" label="How clear were the annotation guidelines?">
    <Choice value="Very Clear"/>
    <Choice value="Clear"/>
    <Choice value="Neutral"/>
    <Choice value="Unclear"/>
    <Choice value="Very Unclear"/>
  </Choices>
  <TextArea name="comments" toName="comments" rows="3" label="Additional comments (optional)" placeholder="Note any edge cases, ambiguities, or concerns..."/>
</View>`

const UTAUT_STUDY = `<View>
  <Header value="Post-Annotations-Fragebogen" level="3"/>

  <Header value="Allgemeine Fragen" level="4"/>
  <Likert name="difficulty" toName="difficulty" min="1" max="7" required="true" label="Es fiel mir leicht die Aufgabe zu lösen."/>
  <Likert name="responsibility" toName="responsibility" min="1" max="7" required="true" label="Ich fühle mich verantwortlich für das von mir eingereichte Ergebnis."/>

  <Header value="Fragen zur KI-Unterstützung (nur beantworten, wenn du in der KI-Gruppe warst)" level="4"/>
  <Likert name="ai_adequate" toName="ai_adequate" min="1" max="7" label="Der Output der KI war auf Anhieb adäquat."/>
  <Likert name="ai_reviewed" toName="ai_reviewed" min="1" max="7" label="Ich habe den Output der KI überprüft."/>
  <Likert name="utaut_pe" toName="utaut_pe" min="1" max="7" label="Ich würde die KI in meiner Arbeit/meinem Studium als nützlich empfinden."/>
  <Likert name="utaut_ee" toName="utaut_ee" min="1" max="7" label="Ich empfinde die KI als einfach zu nutzen."/>
  <Likert name="utaut_att1" toName="utaut_att1" min="1" max="7" label="Die Nutzung der KI ist eine gute Idee."/>
  <Likert name="utaut_att2" toName="utaut_att2" min="1" max="7" label="Die Arbeit mit der KI macht Spaß."/>
  <Likert name="utaut_att3" toName="utaut_att3" min="1" max="7" label="Ich arbeite gerne mit der KI."/>

  <Header value="Anteil an der Fallbearbeitung (nur beantworten, wenn du in der KI-Gruppe warst)" level="4"/>
  <Number name="human_share" toName="human_share" min="0" max="100" label="x Prozent der Fallbearbeitung gehen auf mich zurück." hint="Wert zwischen 0 und 100"/>
  <Number name="ai_share" toName="ai_share" min="0" max="100" label="y Prozent der Fallbearbeitung gehen auf die KI zurück." hint="Wert zwischen 0 und 100"/>

  <Header value="Frage ohne KI (nur beantworten, wenn du NICHT in der KI-Gruppe warst)" level="4"/>
  <Likert name="desired_ai" toName="desired_ai" min="1" max="7" label="Ich hätte mir die KI für die Bearbeitung dieser Aufgabe gewünscht."/>
</View>`

const SELF_ASSESSMENT = `<View>
  <Header value="Vor der Bearbeitung" level="3"/>
  <Likert name="prior_knowledge" toName="prior_knowledge" min="1" max="7" required="true" label="Ich kenne mich mit dem Rechtsgebiet dieser Aufgabe gut aus."/>
  <Likert name="motivation" toName="motivation" min="1" max="7" required="true" label="Ich bin motiviert, die Aufgabe sorgfältig zu bearbeiten."/>
  <Likert name="expected_difficulty" toName="expected_difficulty" min="1" max="7" required="true" label="Ich erwarte, dass die Aufgabe schwierig wird."/>
</View>`

const AI_EXPERIENCE = `<View>
  <Header value="Erfahrung mit KI-Werkzeugen" level="3"/>
  <Choices name="ai_use_frequency" toName="ai_use_frequency" choice="single" required="true" label="Wie oft nutzt du KI-Werkzeuge im Studium oder Beruf?">
    <Choice value="Nie"/>
    <Choice value="Seltener als monatlich"/>
    <Choice value="Monatlich"/>
    <Choice value="Wöchentlich"/>
    <Choice value="Täglich"/>
  </Choices>
  <Likert name="ai_trust" toName="ai_trust" min="1" max="7" required="true" label="Ich vertraue den Antworten von KI-Werkzeugen."/>
</View>`

const GRADER_REFLECTION = `<View>
  <Header value="Zur Korrektur" level="3"/>
  <Likert name="grading_confidence" toName="grading_confidence" min="1" max="7" required="true" label="Ich bin mir bei meiner Bewertung sicher."/>
  <Likert name="grading_difficulty" toName="grading_difficulty" min="1" max="7" required="true" label="Die Bewertung dieser Bearbeitung fiel mir schwer."/>
  <Number name="grading_minutes" toName="grading_minutes" min="0" max="240" label="Wie viele Minuten hast du ungefähr für diese Korrektur gebraucht?"/>
  <TextArea name="grading_note" toName="grading_note" rows="3" label="Anmerkungen zur Korrektur (optional)"/>
</View>`

const GRADER_WORKLOAD = `<View>
  <Header value="Belastung bei der Korrektur" level="3"/>
  <Likert name="mental_demand" toName="mental_demand" min="1" max="7" required="true" label="Die Korrektur war geistig anstrengend."/>
  <Likert name="time_pressure" toName="time_pressure" min="1" max="7" required="true" label="Ich habe mich bei der Korrektur unter Zeitdruck gefühlt."/>
  <Likert name="frustration" toName="frustration" min="1" max="7" required="true" label="Die Korrektur hat mich frustriert."/>
</View>`

export const QUESTIONNAIRE_TEMPLATES: Record<
  QuestionnaireTrigger,
  QuestionnaireTemplate[]
> = {
  before_task: [
    { id: 'self_assessment', xml: SELF_ASSESSMENT },
    { id: 'ai_experience', xml: AI_EXPERIENCE },
  ],
  after_submit: [
    { id: 'confidence_difficulty', xml: CONFIDENCE_DIFFICULTY },
    { id: 'extended', xml: EXTENDED_FEEDBACK },
    { id: 'utaut_study', xml: UTAUT_STUDY },
  ],
  korrektur: [
    { id: 'grader_reflection', xml: GRADER_REFLECTION },
    { id: 'grader_workload', xml: GRADER_WORKLOAD },
  ],
}
