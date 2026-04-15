# Data Formats Guide

This guide provides examples of the best data structure for each annotation template type in BenGER. When importing data, ensure your JSON/CSV/TSV files follow these formats for optimal compatibility.

## Table of Contents
- [General Format Guidelines](#general-format-guidelines)
- [Question Answering](#question-answering)
- [Named Entity Recognition](#named-entity-recognition)
- [Text Classification](#text-classification)
- [Relation Extraction](#relation-extraction)
- [Taxonomy (Hierarchical Classification)](#taxonomy-hierarchical-classification)
- [Machine Translation](#machine-translation)
- [Content Moderation](#content-moderation)
- [Text Summarization](#text-summarization)
- [Import Tips](#import-tips)

## General Format Guidelines

### JSON Format
- Use JSON arrays for multiple items
- Each item should be an object with the required fields
- Field names must match exactly (case-sensitive)

### CSV/TSV Format
- First row must contain field names
- Each subsequent row represents one task
- Use quotes for text containing commas (CSV) or tabs (TSV)

### Plain Text Format
- Each line becomes a separate task
- Best for simple text annotation tasks

## Question Answering

For tasks where annotators answer questions based on given context.

**Required fields:**
- `context`: The reference text or document
- `question`: The question to be answered

### JSON Example
```json
[
  {
    "context": "Das Bürgerliche Gesetzbuch (BGB) ist die zentrale Kodifikation des deutschen allgemeinen Privatrechts. Es wurde am 18. August 1896 verkündet und trat am 1. Januar 1900 in Kraft.",
    "question": "Wann trat das BGB in Kraft?"
  },
  {
    "context": "Die Gesellschaft mit beschränkter Haftung (GmbH) ist eine Kapitalgesellschaft mit eigener Rechtspersönlichkeit. Für ihre Verbindlichkeiten haftet nur das Gesellschaftsvermögen.",
    "question": "Wer haftet für die Verbindlichkeiten einer GmbH?"
  }
]
```

### CSV Example
```csv
context,question
"Das Bürgerliche Gesetzbuch (BGB) ist die zentrale Kodifikation des deutschen allgemeinen Privatrechts. Es wurde am 18. August 1896 verkündet und trat am 1. Januar 1900 in Kraft.","Wann trat das BGB in Kraft?"
"Die Gesellschaft mit beschränkter Haftung (GmbH) ist eine Kapitalgesellschaft mit eigener Rechtspersönlichkeit. Für ihre Verbindlichkeiten haftet nur das Gesellschaftsvermögen.","Wer haftet für die Verbindlichkeiten einer GmbH?"
```

## Named Entity Recognition

For identifying and classifying named entities (persons, organizations, locations) in text.

**Required fields:**
- `text`: The text containing entities to be identified

### JSON Example
```json
[
  {
    "text": "Der Bundesgerichtshof in Karlsruhe hat unter Vorsitz von Dr. Müller entschieden, dass die Deutsche Bank AG zur Zahlung verpflichtet ist."
  },
  {
    "text": "Das Landgericht München I verhandelte den Fall der Siemens AG gegen die Stadt München bezüglich der Vergabe öffentlicher Aufträge."
  }
]
```

### CSV Example
```csv
text
"Der Bundesgerichtshof in Karlsruhe hat unter Vorsitz von Dr. Müller entschieden, dass die Deutsche Bank AG zur Zahlung verpflichtet ist."
"Das Landgericht München I verhandelte den Fall der Siemens AG gegen die Stadt München bezüglich der Vergabe öffentlicher Aufträge."
```

## Text Classification

For categorizing text into predefined classes (e.g., sentiment, document type).

**Required fields:**
- `text`: The text to be classified

**Optional fields:**
- `metadata`: Additional context (will be displayed but not annotated)

### JSON Example
```json
[
  {
    "text": "Die Klage ist begründet. Der Beklagte hat die vertraglichen Pflichten verletzt.",
    "metadata": {"case_id": "2023-AZ-12345", "court": "LG Berlin"}
  },
  {
    "text": "Die Revision wird zurückgewiesen. Die Kostenentscheidung folgt aus § 97 ZPO.",
    "metadata": {"case_id": "2023-BGH-98765", "court": "BGH"}
  }
]
```

### CSV Example
```csv
text,case_id,court
"Die Klage ist begründet. Der Beklagte hat die vertraglichen Pflichten verletzt.",2023-AZ-12345,LG Berlin
"Die Revision wird zurückgewiesen. Die Kostenentscheidung folgt aus § 97 ZPO.",2023-BGH-98765,BGH
```

## Relation Extraction

For identifying relationships between entities in text.

**Required fields:**
- `text`: The text containing entities and their relationships

### JSON Example
```json
[
  {
    "text": "Herr Schmidt ist Geschäftsführer der XYZ GmbH und vertritt diese im Rechtsstreit gegen die ABC AG."
  },
  {
    "text": "Die Müller & Partner Rechtsanwälte vertreten die Deutsche Bahn AG in dem Verfahren vor dem OLG Frankfurt."
  }
]
```

## Taxonomy (Hierarchical Classification)

For classifying text into hierarchical categories.

**Required fields:**
- `text`: The text to be classified hierarchically

### JSON Example
```json
[
  {
    "text": "Anspruch auf Schadensersatz wegen Verletzung des allgemeinen Persönlichkeitsrechts durch Presseveröffentlichung"
  },
  {
    "text": "Kündigung des Mietvertrags wegen Zahlungsverzug gemäß § 543 BGB"
  }
]
```

## Machine Translation

For translating legal texts between languages.

**Required fields:**
- `source_text`: The text to be translated

**Optional fields:**
- `source_lang`: Source language code (e.g., "de", "en")
- `target_lang`: Target language code

### JSON Example
```json
[
  {
    "source_text": "Der Vertrag kommt durch Angebot und Annahme zustande.",
    "source_lang": "de",
    "target_lang": "en"
  },
  {
    "source_text": "The contract is formed by offer and acceptance.",
    "source_lang": "en", 
    "target_lang": "de"
  }
]
```

### CSV Example
```csv
source_text,source_lang,target_lang
"Der Vertrag kommt durch Angebot und Annahme zustande.",de,en
"The contract is formed by offer and acceptance.",en,de
```

## Content Moderation

For reviewing and categorizing content for compliance or safety.

**Required fields:**
- `text`: The content to be moderated

**Optional fields:**
- `source`: Origin of the content
- `author`: Content creator
- `date`: Creation date

### JSON Example
```json
[
  {
    "text": "Stellungnahme zum Gesetzentwurf zur Reform des Insolvenzrechts",
    "source": "legal_blog",
    "author": "Dr. Meyer",
    "date": "2024-01-15"
  },
  {
    "text": "Kommentar zur aktuellen BGH-Entscheidung im Mietrecht",
    "source": "forum",
    "author": "user123",
    "date": "2024-01-16"
  }
]
```

## Text Summarization

For creating summaries of longer legal documents or texts.

**Required fields:**
- `text`: The full text to be summarized

**Optional fields:**
- `title`: Document title
- `type`: Document type (e.g., "verdict", "contract", "statute")

### JSON Example
```json
[
  {
    "text": "BUNDESGERICHTSHOF - URTEIL vom 15. Januar 2024... [full legal text]...",
    "title": "BGH Urteil zum Verbraucherschutz",
    "type": "verdict"
  },
  {
    "text": "VERTRAG über die Lieferung von Waren... [full contract text]...",
    "title": "Liefervertrag XYZ GmbH",
    "type": "contract"
  }
]
```

### CSV Example
```csv
text,title,type
"BUNDESGERICHTSHOF - URTEIL vom 15. Januar 2024... [full legal text]...","BGH Urteil zum Verbraucherschutz",verdict
"VERTRAG über die Lieferung von Waren... [full contract text]...","Liefervertrag XYZ GmbH",contract
```

## Import Tips

### Best Practices
1. **Validate JSON**: Use a JSON validator before importing
2. **UTF-8 Encoding**: Ensure files are UTF-8 encoded for German special characters (ä, ö, ü, ß)
3. **Escape Special Characters**: In JSON, escape quotes and backslashes
4. **Consistent Structure**: All items should have the same fields
5. **Reasonable Size**: Split very large datasets into smaller batches

### Common Issues and Solutions

**Issue**: Import fails with "Invalid JSON"
- **Solution**: Check for missing commas, quotes, or brackets

**Issue**: German characters appear as "?"
- **Solution**: Save file with UTF-8 encoding

**Issue**: Fields not recognized
- **Solution**: Ensure field names match exactly (case-sensitive)

**Issue**: CSV import merges columns
- **Solution**: Use quotes around text containing commas

### File Size Recommendations
- **Optimal**: 100-1000 items per file
- **Maximum**: 10,000 items per file
- **Large datasets**: Use batch import with multiple files

## API Integration

For programmatic data import:

```python
import requests
import json

# Prepare data
data = [
    {
        "text": "Sample legal text for annotation",
        "metadata": {"source": "api"}
    }
]

# Create project and import data
response = requests.post(
    "https://your-instance/api/projects/{project_id}/import",
    headers={"Authorization": "Bearer YOUR_TOKEN"},
    json={"data": data}
)
```

## Need Help?

If you encounter issues with data formats:
1. Check the example for your template type
2. Validate your JSON structure
3. Ensure UTF-8 encoding
4. Contact your administrator for complex imports