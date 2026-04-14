# Task Template System Documentation

## Overview

The Task Template System (Issue #216) provides a unified, flexible configuration system that enables declarative task definitions in BenGER. Instead of hard-coding task types throughout the application, templates define how tasks are structured, displayed, validated, and processed.

## Key Benefits

1. **Flexibility**: Create new task types without code changes
2. **Consistency**: Unified handling across all components
3. **Maintainability**: Centralized configuration reduces code duplication
4. **Extensibility**: Easy to add new field types and behaviors
5. **Validation**: Built-in field validation and data integrity

## Architecture

### Components

1. **Template Schema** (`task_template_schema.py`)
   - Pydantic models for template validation
   - Field types and validation rules
   - JSON Schema generation

2. **Template Service** (`task_template_service.py`)
   - CRUD operations for templates
   - Template application to tasks
   - Default template management

3. **Template Engine** (`templateEngine.ts`)
   - Dynamic form rendering
   - Table column generation
   - LLM prompt generation
   - Response parsing

4. **Database Model** (`models.py`)
   - TaskTemplate table for storing templates
   - Task model extended with template references

5. **API Endpoints** (`main.py`)
   - RESTful API for template management
   - Template validation and application

## Template Structure

### Basic Template Example

```json
{
  "id": "qa_reasoning",
  "name": "Question & Answer with Reasoning",
  "version": "1.0",
  "description": "QA task with reasoning explanation",
  "category": "qa",
  "fields": [
    {
      "name": "question",
      "type": "text_area",
      "display": {
        "annotation": "readonly",
        "table": "column",
        "creation": "editable"
      },
      "source": "task_data",
      "required": true,
      "label": "Question",
      "validation": [
        {
          "type": "minLength",
          "value": 10,
          "message": "Question must be at least 10 characters"
        }
      ]
    },
    {
      "name": "answer",
      "type": "text_area",
      "display": {
        "annotation": "editable",
        "table": "column",
        "creation": "reference"
      },
      "source": "annotation",
      "required": true
    }
  ],
  "display_config": {
    "table_columns": ["question", "answer"],
    "answer_display": {
      "fields": ["answer", "reasoning"],
      "separator": "divider"
    }
  },
  "llm_config": {
    "prompt_template": "Question: {{question}}\nAnswer:",
    "response_parser": "qa_reasoning_parser",
    "temperature": 0.7,
    "max_tokens": 1000
  },
  "evaluation_config": {
    "metrics": [
      {
        "name": "accuracy",
        "type": "exact_match",
        "weight": 0.6
      }
    ],
    "requires_reference": true
  }
}
```

### Field Types

| Type | Description | Use Case |
|------|-------------|----------|
| `text` | Single line text | Names, IDs, short answers |
| `text_area` | Multi-line text | Questions, long answers |
| `radio` | Single choice | Yes/No, single selection |
| `checkbox` | Multiple choice | Multi-select options |
| `rating` | Numeric rating | 1-5 scale ratings |
| `number` | Numeric input | Scores, quantities |
| `date` | Date picker | Deadlines, timestamps |
| `email` | Email input | Contact information |
| `url` | URL input | References, links |
| `rich_text` | Formatted text | HTML content |
| `file_upload` | File attachment | Documents, images |
| `highlight` | Text highlighting | Span annotation |

### Display Modes

| Mode | Description |
|------|-------------|
| `readonly` | Field cannot be edited |
| `editable` | Field can be edited |
| `hidden` | Field is not shown |
| `column` | Show as table column |
| `in_answer_cell` | Show within another field |
| `reference` | Show for reference only |

### Field Sources

| Source | Description |
|--------|-------------|
| `task_data` | Data from task creation |
| `annotation` | User annotation data |
| `generated` | LLM generated data |
| `computed` | Calculated from other fields |

## Creating Custom Templates

### Step 1: Define Template Structure

```json
{
  "id": "custom_classification",
  "name": "Custom Classification Task",
  "version": "1.0",
  "fields": [
    {
      "name": "text",
      "type": "text_area",
      "display": {
        "annotation": "readonly",
        "table": "column",
        "creation": "editable"
      },
      "source": "task_data",
      "required": true
    },
    {
      "name": "category",
      "type": "radio",
      "display": {
        "annotation": "editable",
        "table": "column",
        "creation": "hidden"
      },
      "source": "annotation",
      "required": true,
      "choices": ["Positive", "Negative", "Neutral"]
    },
    {
      "name": "confidence",
      "type": "rating",
      "display": {
        "annotation": "editable",
        "table": "column",
        "creation": "hidden"
      },
      "source": "annotation",
      "validation": [
        {"type": "min", "value": 1},
        {"type": "max", "value": 5}
      ]
    }
  ],
  "display_config": {
    "table_columns": ["text", "category", "confidence"]
  }
}
```

### Step 2: Add Validation Rules

```json
"validation": [
  {
    "type": "required",
    "message": "This field is required"
  },
  {
    "type": "minLength",
    "value": 10,
    "message": "Must be at least 10 characters"
  },
  {
    "type": "pattern",
    "value": "^[A-Z].*",
    "message": "Must start with capital letter"
  }
]
```

### Step 3: Configure LLM Integration

```json
"llm_config": {
  "prompt_template": "Classify the following text:\n\n{{text}}\n\nCategories: {{#each choices}}{{this}}{{#unless @last}}, {{/unless}}{{/each}}\n\nClassification:",
  "response_parser": "classification_parser",
  "system_prompt": "You are a text classification expert.",
  "temperature": 0.3,
  "response_format": "structured",
  "field_mapping": {
    "classification": "category",
    "confidence_score": "confidence"
  }
}
```

### Step 4: Set Up Evaluation

```json
"evaluation_config": {
  "metrics": [
    {
      "name": "classification_accuracy",
      "type": "accuracy",
      "weight": 0.8
    },
    {
      "name": "confidence_correlation",
      "type": "custom",
      "weight": 0.2,
      "config": {
        "evaluator": "confidence_evaluator"
      }
    }
  ],
  "requires_reference": true,
  "threshold": 0.85
}
```

## API Usage

### List Available Templates

```bash
GET /api/templates?category=qa

Response:
{
  "templates": [
    {
      "id": "qa",
      "name": "Question & Answer",
      "version": "1.0",
      "category": "qa",
      "is_system": true
    }
  ],
  "total": 1
}
```

### Create Custom Template

```bash
POST /api/templates
Content-Type: application/json

{
  "template_data": {
    "id": "my_template",
    "name": "My Custom Template",
    "fields": [...],
    "display_config": {...}
  }
}
```

### Apply Template to Task

```bash
POST /api/templates/{template_id}/apply/{task_id}
Content-Type: application/json

{
  "initial_data": {
    "field1": "value1"
  }
}
```

### Validate Data Against Template

```bash
POST /api/templates/{template_id}/validate
Content-Type: application/json

{
  "task_data": {
    "question": "What is AI?",
    "answer": "Artificial Intelligence"
  }
}

Response:
{
  "valid": true,
  "errors": {}
}
```

## Frontend Integration

### Using Template Engine

```typescript
import { templateEngine } from '@/lib/templateEngine'

// Parse template
const parsedTemplate = templateEngine.parseTemplate(template)

// Render annotation form
const formElements = templateEngine.renderAnnotationForm(
  parsedTemplate,
  taskData,
  annotationData,
  (field, value) => updateAnnotation(field, value),
  validationErrors
)

// Generate table columns
const columns = templateEngine.getTableColumns(parsedTemplate, {
  onCellClick: (field, value, row) => handleCellClick(field, value, row)
})

// Generate LLM prompt
const prompt = templateEngine.generatePrompt(parsedTemplate, taskData)

// Parse LLM response
const parsedResponse = templateEngine.parseLLMResponse(parsedTemplate, llmResponse)
```

### Dynamic Field Rendering

```typescript
// In AnnotationForm component
const { data: fieldConfigs } = useQuery(
  ['template-fields', templateId],
  () => api.getTemplateFields(templateId)
)

return (
  <div>
    {fieldConfigs.map(field => (
      <FieldComponent
        key={field.name}
        field={field}
        value={formData[field.name]}
        onChange={(value) => setFormData({...formData, [field.name]: value})}
      />
    ))}
  </div>
)
```

## Migration Guide

### From Hard-coded Task Types to Templates

1. **Identify Task Type Logic**
   ```typescript
   // Before
   if (taskType === 'qa') {
     return <QAForm />
   } else if (taskType === 'mcq') {
     return <MCQForm />
   }
   
   // After
   return <TemplateForm template={template} />
   ```

2. **Update Task Creation**
   ```typescript
   // Before
   const task = await api.createTask({
     task_type: 'qa',
     // hard-coded fields
   })
   
   // After
   const task = await api.createTask({
     template_id: selectedTemplate.id,
     template_data: formData
   })
   ```

3. **Update Data Display**
   ```typescript
   // Before
   const columns = getColumnsForTaskType(taskType)
   
   // After
   const columns = templateEngine.getTableColumns(template)
   ```

## Best Practices

1. **Template Naming**
   - Use descriptive IDs: `legal_qa_german`
   - Version templates: `1.0`, `1.1`, `2.0`
   - Category grouping: `qa`, `classification`, `generation`

2. **Field Design**
   - Keep field names consistent across templates
   - Use meaningful labels and descriptions
   - Provide helpful placeholder text
   - Set appropriate validation rules

3. **Performance**
   - Cache parsed templates
   - Minimize field count
   - Use appropriate field types
   - Optimize display configurations

4. **Validation**
   - Always validate on both frontend and backend
   - Provide clear error messages
   - Use appropriate validation rules
   - Test edge cases

5. **LLM Integration**
   - Use clear prompt templates
   - Handle response parsing errors
   - Set appropriate temperature values
   - Map fields correctly

## Troubleshooting

### Common Issues

1. **Template Not Loading**
   - Check template ID exists
   - Verify JSON syntax
   - Ensure required fields present

2. **Validation Errors**
   - Check field types match data
   - Verify validation rules
   - Ensure required fields have values

3. **Display Issues**
   - Verify display modes are valid
   - Check field references in display_config
   - Ensure table_columns reference existing fields

4. **LLM Generation Problems**
   - Verify prompt template syntax
   - Check field placeholders exist
   - Ensure response parser is implemented

## Future Enhancements

1. **Visual Template Builder**
   - Drag-and-drop interface
   - Live preview
   - Validation testing

2. **Template Marketplace**
   - Share templates
   - Template ratings
   - Usage analytics

3. **Advanced Features**
   - Conditional logic
   - Computed fields
   - Field dependencies
   - Dynamic choices

4. **Integration**
   - Import from other formats
   - Export to Label Studio
   - API compatibility

## Conclusion

The Task Template System transforms BenGER from a rigid, hard-coded task system to a flexible, extensible platform. By defining tasks declaratively through templates, we enable:

- Rapid task type creation
- Consistent user experience
- Easier maintenance
- Better scalability
- Enhanced customization

For questions or support, please refer to the [GitHub repository](https://github.com/your-org/benger) or contact the development team.