---
name: famou-result-visualization
description: Generate interactive visualization pages for feasible solutions produced by Famou evolutionary algorithms. Use this skill when the user mentions "Famou visualization", "visualize this solution", "show feasible solution results", "evolution results", "evolve visualization", or provides a Python-code solution (path planning, scheduling, knapsack, TSP, job scheduling, machine learning, etc.) that needs to be displayed visually. Even if the user just says "help me visualize this solution", "draw it out", or "show me the results", trigger this skill immediately whenever the context involves evolutionary algorithms or optimization problem solutions.
metadata:
  author: famou-group
  version: "2.0"
---

# Famou Evolutionary Algorithm Solution — Result Visualization Skill

**Core goal**: Take an optimization problem solution in Python code form, understand its semantics directly, and generate an interactive HTML page that visually demonstrates **the effect of the solution**.

This is not about showing the evolutionary process — it's about showing **what the solution looks like**: draw the route for path planning, draw the timetable for scheduling, draw the packing layout for knapsack problems, draw the colored graph for graph coloring, etc.

---

## Step 1: Collect Inputs

**Required:**
1. **Problem description** — what optimization problem it is, input scale, constraints
2. **Solution in Python code** — the final solution after Famou evolution (functions, data structures, or strategy code are all acceptable)

**Optional:**
- Evaluation score / fitness value
- Initial solution (for comparison)
- Original problem data (e.g. node coordinates, task list, etc.)

If any required input is missing, ask the user to provide it before proceeding.

---

## Step 2: Understand the Solution → Plan the Visualization

**Read and understand** the user's Python code and problem description directly — no external API calls needed.

### 2.1 Understand the Solution Semantics

Read the code and extract:
- **Problem type**: path planning / scheduling / knapsack / graph theory / job scheduling / bin packing / other
- **Core data structure of the solution**: node sequence? time-slot mapping? selection set? assignment plan?
- **Key values**: coordinates, time slots, capacities, weights, colors, and other concrete data needed for visualization

### 2.2 Determine Visualization Type

Choose the most appropriate `viz_type` based on the problem type:

| Problem Type | viz_type | Visual Representation |
|---|---|---|
| TSP / VRP / Path Planning | `path_map` | SVG coordinate system + node-connected route |
| Scheduling / Timetable | `schedule_grid` | Table heatmap with colored blocks |
| Knapsack / Bin Packing | `packing_rect` | SVG stacked rectangle containers |
| Graph Coloring / Community Detection | `graph_color` | Node-colored graph |
| Job Scheduling / Project Planning | `gantt` | Horizontal Gantt chart |
| Before/After Comparison / Multi-metric | `bar_compare` | Comparative bar chart |
| ML / Neural Networks / Hyperparameter Tuning | `ml_viz` | Network structure / training curve / hyperparameter heatmap |
| Other / Complex Strategies | `custom` | Key metrics dashboard + text description |

### 2.3 Extract Rendering Data

Read the code directly and organize the concrete values needed for rendering, for example:
- `path_map`: list of node coordinates, visit order, total distance
- `schedule_grid`: resource list, time slots, each assignment as (resource, time slot, name)
- `packing_rect`: container dimensions, each item as (x, y, w, h, label, value)
- `gantt`: task list, each item containing (name, start, end, resource)

---

## Step 3: Generate the HTML Visualization File

Write and output the HTML file directly to `famou_viz_result.html` (or a user-specified path).

### Page Layout

```
┌──────────────────────────────────────────────────────────┐
│  [Problem Type Tag]  Problem Summary       Key Metric Cards  │
├────────────────────────────────────┬─────────────────────┤
│                                    │                     │
│   Main Visualization Area          │   Solution Highlights│
│   (visual center, ≥50% of page)    │                     │
│   Route / Timetable / Packing /    │   Score / Improvement│
│   Gantt Chart                      │   Display           │
├────────────────────────────────────┴─────────────────────┤
│   (Optional) Before/After Comparison / Additional Notes   │
└──────────────────────────────────────────────────────────┘
```

### Design Guidelines

- **Dark tech aesthetic**: background `#030810`, cards `#080f1e`, borders `#112240`
- **Accent colors**: primary `#00c8ff` (blue) paired with `#00ff88` (green) for highlights
- **Fonts**: body text `Noto Sans SC`, numbers/code `IBM Plex Mono` (via Google Fonts CDN)
- **Entrance animation**: each section fades up in sequence (`fadeUp` with increasing `animation-delay`)
- **Main visualization animation**: routes drawn segment by segment, bars grow from the bottom, nodes pop in
- **Interactivity**: hovering over nodes / grid cells / bars shows a tooltip
- **Tooltip**: fixed-position, follows the mouse, shows detailed values

### File Template

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Famou Solution Visualization — {Problem Name}</title>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/react/18.2.0/umd/react.production.min.js"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/react-dom/18.2.0/umd/react-dom.production.min.js"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/babel-standalone/7.23.5/babel.min.js"></script>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Noto+Sans+SC:wght@400;500;700&display=swap" rel="stylesheet">
  <style>
    /* All styles inlined — no external CSS dependencies */
    /* Includes: CSS variables, animation keyframes, card/tag/tooltip/skeleton base classes */
  </style>
</head>
<body>
  <div id="root"></div>
  <script type="text/babel">
    const { useState, useEffect, useRef } = React;

    // ── Data extracted from the solution (hardcoded from code analysis) ──
    const SOLUTION_DATA = { /* ... */ };

    // ── Visualization components ──
    // Implement the component corresponding to viz_type

    // ── Page skeleton ──
    function App() { /* Metric cards + main visualization + highlights list */ }

    ReactDOM.render(<App />, document.getElementById('root'));
  </script>
</body>
</html>
```

---

## Notes

- **Read data directly from the code**: Extract key values from the Python solution (coordinates, sequences, mappings, etc.) and hardcode them into the `SOLUTION_DATA` constant in the HTML — do not execute the Python code, only read its data literals.
- **Visualization must faithfully represent the solution**: Show "what this solution looks like", not the evolutionary history or algorithm flow.
- **Main visualization area should be large**: It is the visual center of the page, occupying at least 50% of the page.
- **Adapt to data scale**: When the number of nodes/tasks exceeds 100, consider sampling or aggregating to avoid visual clutter.
- **Graceful degradation**: If the problem type cannot be identified, fall back to the `custom` dashboard showing key metrics.
- **Self-contained**: All dependencies are loaded via CDN; the file can be opened offline (CDN links can be replaced with local copies).