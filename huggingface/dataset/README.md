---
dataset_info:
  features:
    - name: scenario_id
      dtype: string
    - name: category
      dtype: string
    - name: incidents
      dtype: string
    - name: cmdb_items
      dtype: string
    - name: risk_factors
      dtype: string
    - name: gold_standard_rfc
      dtype: string
license: mit
task_categories:
  - text-generation
  - text2text-generation
language:
  - en
tags:
  - itil
  - itsm
  - change-management
  - incident-management
  - cmdb
  - servicenow
  - benchmark
  - enterprise-ai
  - rfc-generation
pretty_name: ITSM Change Management Benchmark
size_categories:
  - n<1K
---

# ITSM Change Management Benchmark

The first public dataset for evaluating AI agents on IT Service Management (ITSM) tasks, specifically ITIL Change Management RFC generation.

## Dataset Description

This dataset contains structured ITSM data across three realistic enterprise scenarios, designed to benchmark AI agents that generate or evaluate Request for Change (RFC) documents against ITIL v4 standards.

### Scenarios

| Scenario | Category | Incidents | CMDB Items | Risk Factors |
|----------|----------|-----------|------------|--------------|
| Database Migration (PostgreSQL 16) | Infrastructure | 5 | 23 | 8 |
| Security Patch (Log4Shell) | Security | 5 | 20 | 10 |
| Cost Optimization (Auto-Scaling) | Infrastructure | 5 | 25 | 9 |

### Data Contents

**Incidents** — Structured incident records with:
- Unique ID, title, severity (P1-P4), category
- Detailed description with technical specifics
- Affected configuration items (CI references)
- Resolution details and MTTR (Mean Time To Repair)

**CMDB Items** — Configuration Management Database entries with:
- CI identifier, type classification, description
- Business criticality rating (Critical/High/Medium/Low)
- Infrastructure details (specifications, versions, counts)

**Scenario Metadata** — Context for each change scenario:
- Affected services, estimated cost, business value
- Risk factors with specific technical and organizational risks
- Rollback plans and testing status
- Timeline and deployment strategy

**Gold Standard RFCs** — Complete, multi-iteration RFC outputs showing:
- 6-dimension scoring (quality, compliance, risk, business value, technical readiness, stakeholder confidence)
- Executive summaries with CAB approval probability
- Critical issues identified per iteration
- Improvement recommendations with effort estimates
- Change category assessments

## Intended Use

### Benchmarking AI Agents
Evaluate whether an AI agent can:
1. Generate a complete, ITIL-compliant RFC from incident and CMDB data
2. Identify critical issues and risks
3. Iteratively improve the RFC based on feedback
4. Produce CAB-ready documentation

### Evaluation Metrics
Compare agent output against gold standard RFCs on:
- 6-dimension score correlation
- Critical issue identification (precision/recall)
- ITIL section completeness
- Iteration improvement rate

### Training Data
Use as few-shot examples or fine-tuning data for:
- ITSM document generation models
- RFC quality evaluation models
- Risk assessment classifiers

### ServiceNow PDI Seeding
The companion [ITIL Reflexion Agent repo](https://github.com/VuduVations/itil-reflexion-agent) includes a script that populates a ServiceNow Personal Developer Instance with scenario-specific CMDB items and incidents derived from this dataset. Use it to stand up a realistic ServiceNow test environment for evaluating ITSM-focused agents against live REST API calls.

## Dataset Structure

```
data/
├── incidents.json      # 15 incident records (5 per scenario)
├── cmdb.json           # 68 CMDB items across 3 scenarios
└── scenarios.json      # 3 scenario definitions with metadata
```

## Usage

```python
from datasets import load_dataset

dataset = load_dataset("VuduVations/itsm-change-management-benchmark")
```

Or load individual files:

```python
import json

with open("data/incidents.json") as f:
    incidents = json.load(f)

# Get database migration incidents
db_incidents = incidents["db-migration"]
print(f"{len(db_incidents)} incidents")
print(db_incidents[0]["title"])
```

## Citation

```bibtex
@dataset{vuduvations2024itsm,
  title={ITSM Change Management Benchmark},
  author={Vuduvations},
  year={2025},
  url={https://huggingface.co/datasets/VuduVations/itsm-change-management-benchmark},
  license={MIT}
}
```

## Related

- [ITIL Reflexion Agent](https://github.com/vuduvations/itil-reflexion-agent) — Open-source LangGraph agent that uses this dataset
- [Technical Paper](https://github.com/vuduvations/itil-reflexion-agent/blob/main/docs/technical-paper.pdf)
- [Vuduvations](https://vuduvations.io)

## License

MIT — free to use for research, evaluation, training, and commercial applications.
