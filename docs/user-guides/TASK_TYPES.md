# Task Types Documentation

BenGER supports two primary task types for annotation and evaluation:

## QA (Question & Answer)

### Purpose
Simple question-answer pairs for general knowledge, facts, and straightforward responses.

### Features
- **Single/Bulk Mode**: Create individual questions or import multiple questions at once
- **JSON Import/Export**: Full round-trip support with metadata preservation
- **Template System**: Configurable prompts and instructions
- **Response Tracking**: Human annotations and LLM model responses
- **Rich Metadata**: Difficulty levels, tags, domains, and performance metrics

### Data Structure

#### Single Question Format
```json
{
  "question": "What is the capital of France?",
  "reference_answer": "Paris",
  "difficulty_level": "easy",
  "domain": "geography",
  "tags": ["geography", "europe", "capitals"]
}
```

#### Bulk Questions Format
```json
{
  "name": "General Knowledge QA",
  "description": "Simple question-answer task for testing general knowledge",
  "difficulty_level": "medium",
  "domain": "general",
  "language": "de",
  "system_prompt": "Sie sind ein hilfreicher KI-Assistent. Beantworten Sie Fragen präzise und korrekt.",
  "instruction_prompts": [
    {
      "text": "Beantworten Sie die Frage direkt und präzise.",
      "purpose": "Baseline Evaluation"
    }
  ],
  "questions": [
    {
      "question": "Wie viele Kontinente gibt es auf der Erde?",
      "reference_answer": "Sieben",
      "tags": ["geography", "general-knowledge"],
      "difficulty_level": "easy"
    }
  ]
}
```

#### Export Format with Annotations
```json
{
  "questions": [
    {
      "id": "1",
      "question": "What is the capital of France?",
      "reference_answer": "Paris",
      "human_responses": {
        "human_annotator_001": {
          "answer": "Paris",
          "confidence_score": 0.9,
          "annotated_at": "2024-01-01T10:00:00Z",
          "annotation_time_seconds": 45,
          "annotator_experience": "expert"
        }
      },
      "model_responses": {
        "gpt-4": {
          "answer": "Paris",
          "confidence_score": 0.95,
          "generated_at": "2024-01-01T09:00:00Z",
          "usage_stats": {
            "prompt_tokens": 30,
            "completion_tokens": 10,
            "total_tokens": 40
          }
        }
      }
    }
  ]
}
```

### Use Cases
- General knowledge assessment
- Factual question answering
- Educational content validation
- Simple information retrieval tasks

---

## QAR (Question Answering & Reasoning)

### Purpose
Complex legal and analytical tasks requiring detailed reasoning and justification.

### Features
- **Answer + Reasoning**: Structured responses with detailed justification
- **Legal Domain Focus**: Specialized for German law and legal analysis
- **Binary Decisions**: Yes/No answers with comprehensive reasoning
- **Enhanced Metadata**: Legal case information, reasoning quality metrics
- **Bulk Processing**: Handle multiple legal cases efficiently

### Data Structure

#### Single Question Format
```json
{
  "question": "Ist eine fristlose Kündigung ohne wichtigen Grund möglich?",
  "reference_answer": {
    "answer": "Nein",
    "reasoning": "Nach § 626 BGB ist eine fristlose Kündigung nur bei Vorliegen eines wichtigen Grundes möglich..."
  },
  "difficulty_level": "medium",
  "domain": "arbeitsrecht",
  "tags": ["kündigungsrecht", "arbeitsrecht", "§626-bgb"]
}
```

#### Bulk Questions Format
```json
{
  "name": "Arbeitsrecht Analyse",
  "description": "Rechtliche Fallanalyse im deutschen Arbeitsrecht",
  "difficulty_level": "hard",
  "domain": "arbeitsrecht",
  "language": "de",
  "system_prompt": "Sie sind ein erfahrener Jurist mit Expertise im deutschen Zivilrecht und Arbeitsrecht.",
  "instruction_prompts": [
    {
      "text": "Analysieren Sie rechtliche Sachverhalte präzise...",
      "purpose": "Legal Analysis"
    }
  ],
  "questions": [
    {
      "question": "Ist eine Kündigung bei Krankheit zulässig?",
      "reference_answer": {
        "answer": "Ja",
        "reasoning": "Eine krankheitsbedingte Kündigung ist unter bestimmten Voraussetzungen möglich..."
      },
      "tags": ["krankheit", "kündigung", "arbeitsrecht"],
      "difficulty_level": "hard"
    }
  ]
}
```

#### Export Format with Annotations
```json
{
  "questions": [
    {
      "id": "1",
      "question": "Ist eine fristlose Kündigung ohne wichtigen Grund möglich?",
      "reference_answer": {
        "answer": "Nein",
        "reasoning": "Nach § 626 BGB ist eine fristlose Kündigung nur bei Vorliegen eines wichtigen Grundes möglich..."
      },
      "human_responses": {
        "legal_expert_001": {
          "answer": "Nein",
          "reasoning": "Detaillierte juristische Begründung...",
          "confidence_score": 0.95,
          "annotated_at": "2024-01-01T10:00:00Z",
          "annotation_time_seconds": 900,
          "annotator_experience": "expert",
          "annotator_background": "legal_specialist"
        }
      },
      "model_responses": {
        "legal-llm-v1": {
          "answer": "Nein",
          "reasoning": "KI-generierte Rechtsbegründung...",
          "confidence_score": 0.88,
          "generated_at": "2024-01-01T09:00:00Z",
          "usage_stats": {
            "prompt_tokens": 150,
            "completion_tokens": 300,
            "total_tokens": 450
          }
        }
      }
    }
  ]
}
```

### Use Cases
- Legal case analysis
- Contract review
- Regulatory compliance assessment
- Complex reasoning tasks requiring justification

---

## Common Features

### Import/Export Workflow
1. **Import JSON**: Upload bulk question data with existing annotations
2. **Annotation**: Human annotators provide responses in Native Annotation System
3. **LLM Generation**: Generate model responses for evaluation
4. **Export**: Download complete datasets with all responses and metadata

### Supported Metrics
- **QA**: exact_match, f1, token_f1, bleu, rouge_l, semantic_similarity, answer_relevance
- **QAR**: All QA metrics plus specialized reasoning evaluation

### Template System
Both task types support:
- **System Prompts**: Define AI assistant role and expertise
- **Instruction Prompts**: Multiple evaluation strategies with different purposes
- **Configurable Templates**: Custom Native Annotation System configurations

### File Formats
- **Input**: JSON files with question data
- **Export**: JSON files with complete annotation data
- **Templates**: JSON structure with prompts and configuration

---

## Migration from Old Task Types

Previously supported task types (`text_classification`, `summarization`, `extraction`) have been consolidated into the QA/QAR system:

- **Text Classification** → Use QA with categorical answers
- **Summarization** → Use QAR with reasoning-based responses  
- **Extraction** → Use QA with specific extraction questions

This consolidation provides:
- Unified data formats
- Consistent evaluation metrics
- Simplified maintenance
- Better scalability

---

## Getting Started

1. **Choose Task Type**: QA for simple answers, QAR for complex reasoning
2. **Prepare Data**: Use provided JSON examples as templates
3. **Import/Create**: Upload JSON or create individual questions
4. **Configure**: Set up system and instruction prompts
5. **Annotate**: Use Native Annotation System for human annotations
6. **Evaluate**: Generate and evaluate LLM responses
7. **Export**: Download complete datasets for analysis 