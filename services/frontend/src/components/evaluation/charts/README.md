# Evaluation Charts

This directory contains specialized chart components for evaluation results visualization.

## SignificanceHeatmap

The `SignificanceHeatmap` component visualizes pairwise statistical significance between models using a heatmap display.

### Features

- **Lower Triangular Matrix**: Shows each comparison only once to avoid redundancy
- **Color-Coded Effect Sizes**: Blue indicates Model A > Model B, Red indicates Model B > Model A
- **Significance Stars**: Overlay of \*, **, \*** indicating p-value thresholds
- **Interactive Tooltips**: Hover to see detailed statistics (p-value, effect size)
- **Click Handler**: Click cells to trigger custom actions (e.g., show detailed comparison)
- **Comprehensive Legend**: Explains color scale and significance levels

### Usage

```typescript
import { SignificanceHeatmap } from '@/components/evaluation/charts/SignificanceHeatmap'

function EvaluationResults() {
  const modelIds = ['gpt-4', 'claude-3', 'llama-3']

  const significanceData = [
    {
      model_a: 'gpt-4',
      model_b: 'claude-3',
      p_value: 0.003,
      significant: true,
      effect_size: 0.42,
      stars: '**'
    },
    {
      model_a: 'gpt-4',
      model_b: 'llama-3',
      p_value: 0.0001,
      significant: true,
      effect_size: 0.89,
      stars: '***'
    },
    {
      model_a: 'claude-3',
      model_b: 'llama-3',
      p_value: 0.045,
      significant: true,
      effect_size: 0.31,
      stars: '*'
    }
  ]

  const handleCellClick = (modelA: string, modelB: string) => {
    console.log(`Clicked comparison: ${modelA} vs ${modelB}`)
    // Open detailed comparison modal, etc.
  }

  return (
    <SignificanceHeatmap
      modelIds={modelIds}
      metric="F1 Score"
      significanceData={significanceData}
      height={500}
      onCellClick={handleCellClick}
    />
  )
}
```

### Props

| Prop               | Type                                       | Required | Default | Description                          |
| ------------------ | ------------------------------------------ | -------- | ------- | ------------------------------------ |
| `modelIds`         | `string[]`                                 | Yes      | -       | Array of model identifiers           |
| `metric`           | `string`                                   | Yes      | -       | Name of the metric being compared    |
| `significanceData` | `SignificanceEntry[]`                      | Yes      | -       | Array of pairwise comparison results |
| `height`           | `number`                                   | No       | 400     | Height of the chart in pixels        |
| `onCellClick`      | `(modelA: string, modelB: string) => void` | No       | -       | Callback when a cell is clicked      |

### SignificanceEntry Interface

```typescript
interface SignificanceEntry {
  model_a: string // First model ID
  model_b: string // Second model ID
  p_value: number // Statistical p-value
  significant: boolean // Whether difference is significant
  effect_size: number // Effect size (Cohen's d or similar)
  stars: string // "", "*", "**", or "***"
}
```

### Color Scale

- **Blue (#1e40af to #60a5fa)**: Positive effect size (Model A performs better)
- **White (#ffffff)**: No effect (models perform similarly)
- **Red (#dc2626 to #f87171)**: Negative effect size (Model B performs better)

### Significance Levels

- `***` (p < 0.001): Highly significant
- `**` (p < 0.01): Very significant
- `*` (p < 0.05): Significant
- (empty) (p ≥ 0.05): Not significant

### Integration Notes

This component is designed to work with statistical evaluation results from the backend. The significance data should be computed using appropriate statistical tests (e.g., paired t-test, Wilcoxon signed-rank test) with proper multiple comparison corrections (e.g., Bonferroni, Holm-Bonferroni).

### Dependencies

- `react-plotly.js`: For interactive heatmap visualization
- `plotly.js`: Underlying plotting library

Both are already included in the project dependencies.
