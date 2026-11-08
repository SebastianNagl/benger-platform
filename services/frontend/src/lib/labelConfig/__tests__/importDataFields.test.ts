/**
 * @jest-environment jsdom
 */

import {
  extractImportDataFields,
  parseLabelConfig,
  type ParsedComponent,
} from '../parser'

function fieldsOf(xml: string) {
  const parsed = parseLabelConfig(xml)
  if ('message' in parsed) throw new Error(parsed.message)
  return extractImportDataFields(parsed as ParsedComponent)
}

describe('extractImportDataFields', () => {
  it('treats the exam Angabe side bindings as optional', () => {
    expect(
      fieldsOf(`<View>
        <Angabe name="angabe" value="$sachverhalt" toName="sachverhalt"
                bearbeitervermerk="$bearbeitervermerk"
                zusatzmaterial="$zusatzmaterial" linkedTo="gliederung"/>
        <Loesung name="loesung" toName="sachverhalt" required="true"/>
      </View>`),
    ).toEqual({
      required: ['sachverhalt'],
      optional: ['bearbeitervermerk', 'zusatzmaterial'],
    })
  })

  it('requires every value binding, nested ones included', () => {
    expect(
      fieldsOf(`<View>
        <Text name="q" value="$question"/>
        <View><Text name="c" value="$context"/></View>
      </View>`),
    ).toEqual({ required: ['question', 'context'], optional: [] })
  })

  it('requires every $ prop of a required component', () => {
    expect(
      fieldsOf(`<View>
        <Text name="t" value="$text" hint="$hint" required="true"/>
        <Text name="u" value="$other" hint="$note"/>
      </View>`),
    ).toEqual({ required: ['text', 'hint', 'other'], optional: ['note'] })
  })

  it('lists a field bound both ways only once, as required', () => {
    expect(
      fieldsOf(`<View>
        <Text name="a" value="$body" title="$title"/>
        <Header value="$title"/>
      </View>`),
    ).toEqual({ required: ['body', 'title'], optional: [] })
  })

  it('ignores plain attribute values and a bare $', () => {
    expect(
      fieldsOf(`<View>
        <Header value="Angabe"/>
        <Text name="x" value="$" placeholder="5 $ pro Stunde"/>
      </View>`),
    ).toEqual({ required: [], optional: [] })
  })
})
