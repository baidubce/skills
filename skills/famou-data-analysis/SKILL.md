---
name: famou-data-analysis
description: A data analysis skill for understanding datasets, analyzing data, building data processing pipelines, and summarizing analytical results. Use this skill when the user mentions "analyze data", "data processing", "data exploration", "statistical analysis", "data cleaning", "data summarization", "create a data report", "understand this dataset", or "take a look at this CSV/Excel/dataset". Even if the user simply says "help me look at this data" or "analyze this", trigger this skill whenever the context involves a data file or dataset. Also invoke this skill if data analysis is required during Famou problem definition.
metadata:
  author: famou-group
  version: "2.0"
---

# Data Analysis Skill

## Analysis Goals

The core objectives of a data analysis task are:

1. **Understand the data**: Clarify what the data is, where it comes from, and what business meaning it carries — not just read the file
2. **Assess data quality**: Identify missing values, duplicates, anomalies, and formatting inconsistencies; evaluate data trustworthiness
3. **Discover patterns and insights**: Use statistics and exploration to surface meaningful patterns, trends, anomalies, and correlations
4. **Design a processing pipeline**: Based on the actual data issues, design a reproducible and well-reasoned cleaning and transformation plan
5. **Summarize findings**: Deliver conclusions in clear, business-relevant language — not just a pile of statistics

---

## Constraints

**Always follow these constraints throughout the analysis:**

- **Do not modify raw data without permission**: Always inform the user and explain the reason before performing any cleaning or transformation
- **Do not over-assume data meaning**: When column names are unclear, ask the user for clarification rather than guessing
- **Do not ignore data quality issues**: Anomalies, missing values, and inconsistencies must be explicitly flagged — never silently worked around
- **Do not rigidly apply a fixed pipeline**: Data formats vary widely; adapt the analysis approach to the actual situation
- **Do not stray from the user's goal**: Always keep the analysis depth and direction anchored to "what problem is the user trying to solve"

---

## Best Practices

### Understand first, then act
After receiving data, prioritize understanding the context: What is the business scenario? What is the user's analytical goal? This determines which columns matter, what counts as "anomalous", and how to handle missing values.

### Explain results in business language
Don't just output statistics — explain what they mean. "The mean is 3200" is less useful than "The average order value is approximately $3,200, but the median is only $1,800, suggesting a small number of high-value orders are inflating the mean."

### Triage data quality issues by severity
- **Blocking issues** (e.g., critical columns entirely empty, widespread primary key duplication): Stop and inform the user; wait for confirmation before proceeding
- **Decision-required issues** (e.g., high missing rates, ambiguous outliers): Present the tradeoffs of each handling option and let the user choose
- **Minor issues** (e.g., scattered format inconsistencies, leading/trailing whitespace): Handle directly, but document them in the report

### Make the processing pipeline explainable
Every operation should be answerable with "why did we do this?", for example:
- "Filled with the median because this column is right-skewed and the mean is heavily influenced by outliers"
- "Dropped this column because the missing rate is 78%, making it unusable"

### Back every conclusion with data
Each insight should be accompanied by specific numbers as evidence; avoid subjective judgments unsupported by data.

### Environment & Tools
- File paths: Uploaded files are at `/mnt/user-data/uploads/`; save output files to `/mnt/user-data/outputs/`
- Encoding issues with non-ASCII data: Try `utf-8` first; fall back to `latin-1` or `cp1252` if needed
- Chart font rendering: Set `matplotlib.rcParams['font.sans-serif'] = ['DejaVu Sans']` for reliable rendering
- CSV output for Excel: Use `encoding='utf-8-sig'` to prevent encoding issues when opening in Excel

---

## Analysis Report Format

Regardless of the analysis path taken, the final summary report should include:

```
## Data Analysis Report

### Data Overview
(Dataset size, source, time range, description of key fields)

### Data Quality
(Issues found, severity level, actions taken or items pending confirmation)

### Key Findings
(3–5 most important insights, each supported by data)

### Processing Pipeline
(What transformations were applied to the data and why)

### Recommendations
(Suggestions for data improvement, directions for deeper analysis)
```

---

## Examples

The following examples show how to apply the goals and constraints above when facing different types of data.

### Example A: E-commerce Order Data Analysis

**Scenario**: The user uploads an order CSV with columns for Order ID, Order Time, Product Category, Amount, User City, and Payment Status, and wants to understand "overall sales performance."

**Analysis approach**:
- Confirm the time range first — this is the baseline context for any sales analysis
- Check the Amount column for negative values (refunds? data entry errors?) and zero values (require business explanation)
- The distribution of Payment Status determines the definition of "valid orders"
- Aggregate by time to spot trends; break down by category and city for composition analysis

**Quality issue handling example**:
> Found 12 rows with negative values in the "Amount" column. In sales data, negatives typically represent refund records. Recommendation: filter them out when analyzing gross revenue; keep them when analyzing net income. Please confirm your analysis goal before we proceed.

**Key findings example**:
> - March revenue grew 34% month-over-month, primarily driven by the "Electronics" category (contributing 61% of the incremental growth)
> - New York and Los Angeles together account for 47% of all orders, but average order value is 15% below the average for mid-tier cities
> - Payment failure rate is 8.3%, above the typical industry benchmark of 2–5%; recommend investigating the payment flow

---

### Example B: Messy Survey Data

**Scenario**: The user uploads an Excel file with multiple sheets, inconsistent column names (some say "Q1", others say "Question 1"), merged cells, and scattered blank rows and columns.

**First step**: Don't rush into analysis — first surface the structural issues to the user:

> This file contains 3 sheets, and there are several structural issues to clarify before we proceed:
> 1. Sheet1 and Sheet2 have different column names — are these different batches of the same survey, or entirely different surveys?
> 2. Rows 5–8 are blank — is it safe to remove them?
> 3. The "Q3_Other" column is 92% empty — is this a low open-response rate, or a data export issue?
>
> Once confirmed, I'll design a cleaning plan.

**Constraint in action**: Column meanings are not assumed, sheets are not merged arbitrarily — issues are surfaced first and the user is asked to confirm.

---

### Example C: User Requests "Clean the Data and Output a Processed File"

**Processing log example** (provided alongside the output file):

```
Data Processing Log
Source file:  sales_2024.csv  (8,412 rows × 15 columns)
Output file:  sales_2024_cleaned.csv  (8,203 rows × 13 columns)

Changes:
1. Removed duplicate rows: deleted 89 fully duplicate records
2. Dropped "Notes2" column: 96% missing, no useful information
3. Dropped "Internal Code" column: user confirmed it is not needed for analysis
4. Standardized Amount column: converted "¥1,200.00" format to numeric 1200.0 (203 rows affected)
5. Standardized Date column: unified to YYYY-MM-DD format (source had mixed MM/DD/YYYY and written-out date formats)
6. Missing value handling:
   - "City" column: 34 missing values → filled with "Unknown" (user confirmed)
   - "Amount" column: 86 missing values → left blank (user confirmed these are anomalous records that should not be imputed)
```