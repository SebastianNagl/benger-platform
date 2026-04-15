# IAA System User Guide

## Quick Start

The Inter-Annotator Agreement (IAA) system helps you measure and improve annotation quality by tracking how well annotators agree with each other.

## Key Concepts

### What is Agreement?
When multiple people annotate the same data, we want them to agree. High agreement = high quality data.

### Agreement Scores
- **1.0 (100%)**: Perfect agreement - everyone chose the same answer
- **0.5 (50%)**: Moderate agreement - some disagreement exists  
- **0.0 (0%)**: No agreement - everyone chose different answers
- **< 0**: Worse than random chance!

## How to Use IAA in BenGER

### 1. Prerequisites
- Create a project with tasks
- Have at least 2 users annotate the same tasks
- The system automatically calculates agreement

### 2. Viewing Agreement Scores

#### Option A: Global Analytics Page
Navigate to `/analytics` to see agreement across all projects:
- Select a project from the dropdown
- View agreement metrics in the Quality Control tab
- See which tasks have low agreement

#### Option B: Project Data Page
1. Go to Projects list
2. Click on a project
3. Click "Project Data"
4. Agreement indicators appear next to tasks with multiple annotations

### 3. Understanding the Visualizations

#### Agreement Score Component
Shows scores with color coding:
- 🟢 Green (>0.6): Good agreement
- 🟡 Yellow (0.4-0.6): Moderate, needs attention
- 🔴 Red (<0.4): Poor, requires action

#### Agreement Matrix
A heatmap showing pairwise agreement between annotators:
- Darker green = better agreement
- Red cells = problematic pairs
- Helps identify annotators who consistently disagree

#### Agreement Timeline
Track how agreement changes over time:
- See if quality is improving
- Identify when problems started
- Monitor the effect of training

#### Consensus View
Side-by-side comparison for resolving conflicts:
- See what each annotator chose
- Identify the source of disagreement
- Make final decisions on disputed items

### 4. Setting Quality Thresholds

Configure automatic actions based on agreement scores:

1. Go to Agreement Settings
2. Set thresholds:
   - Low threshold (e.g., 0.2): Triggers review
   - Moderate threshold (e.g., 0.4): Flags for attention
   - Good threshold (e.g., 0.6): Acceptable quality

3. Choose actions:
   - **FLAG**: Mark for attention
   - **REQUIRE_REVIEW**: Send to senior annotator
   - **ADD_ANNOTATOR**: Get another opinion
   - **ESCALATE**: Notify project manager

### 5. Common Workflows

#### Finding Problems
1. Check overall project agreement
2. Filter for low-agreement tasks
3. Use Consensus View to see disagreements
4. Identify patterns in conflicts

#### Improving Quality
1. Review low-agreement tasks
2. Clarify annotation guidelines
3. Provide additional training
4. Re-annotate problematic items

#### Monitoring Progress
1. Set up thresholds and alerts
2. Check Agreement Timeline regularly
3. Compare annotator pairs in the matrix
4. Track improvement over time

## Best Practices

### For Project Managers
- Set realistic thresholds (0.6-0.7 is often good)
- Review low-agreement tasks weekly
- Use the matrix to pair compatible annotators
- Document resolution decisions

### For Annotators
- Consistency is key
- Ask questions when instructions are unclear
- Review consensus decisions to learn
- Check your agreement scores regularly

### For Data Scientists
- Use agreement scores to filter training data
- Higher agreement = more reliable labels
- Consider weighted voting based on agreement
- Export agreement metrics for analysis

## Metrics Explained

### Cohen's Kappa (κ)
- For 2 annotators only
- Accounts for agreement by chance
- Most common metric

### Fleiss' Kappa
- Extension of Cohen's for 3+ annotators
- Good for classification tasks
- Industry standard

### Krippendorff's Alpha (α)
- Handles missing data gracefully
- Works with any number of annotators
- Most flexible metric

### Percent Agreement
- Simple percentage of matching annotations
- Easy to understand
- Doesn't account for chance

## Troubleshooting

### "No agreement data available"
- Ensure multiple users have annotated the same tasks
- Check that annotations are submitted (not drafts)
- Verify project has IAA enabled

### Low agreement scores
- Review annotation guidelines
- Check for ambiguous tasks
- Ensure consistent training
- Consider task difficulty

### Agreement not updating
- Calculations may be cached (5 min)
- Trigger manual recalculation via API
- Check for incomplete annotations

## API Integration

```python
# Example: Get project agreement
import requests

response = requests.get(
    f"http://api/agreement/projects/{project_id}",
    headers={"Authorization": f"Bearer {token}"}
)

data = response.json()
print(f"Overall agreement: {data['overall_agreement']}")
print(f"Tasks needing review: {data['low_agreement_count']}")
```

## Advanced Features

### Weighted Agreement
Account for task difficulty when calculating overall scores

### Confidence Intervals
Statistical confidence bounds on agreement estimates

### Active Learning Integration
Use agreement to select items for model training

### Custom Metrics
Define project-specific agreement calculations