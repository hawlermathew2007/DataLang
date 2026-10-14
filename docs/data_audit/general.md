# Goals
Generally about creating eval for data governance program to verify whether:

- Policies are enforced
- Roles are accountable
- Controls operate consistently
- Measure data quality (not my part yet)
- Data classification is classified correctly  (not sure yet)
- Data linage is showing the data flow correctly (not sure yet)

Others: Audit without reading file content? Suggestion mechanism? Maintaining data integrity? Collaboration?

Us:

- Data linage is working (checking health)
- Policies: Make sure it follow PDPA (Correct decorative policy lang)
- Roles: for auditors, Users and LLM are accountable
- Controls: 
    - Make sure Masking PII, Cross Check, Active DB ok... anything about operation is doing ok  
    - Make sure that an auditor cannot view file content 

# Research

- Steps of data audit
- Scoring governance maturity (how well, effectively, and systematically an organization manages, secures, and utilizes its data governance processes)

# Steps of data audit

Standard audit steps:

1. Define Scope & Objectives: Determine the target systems, business priorities, and regulatory boundaries.
2. Inventory Data Assets: Map data sources, cloud/legacy environments, pipelines, and storage locations.
3. Evaluate Controls & Quality: Run data profiling, check for duplicate or missing records, and inspect access logs.
4. Report & Prioritize: Classify findings into compliant vs. non-compliant items, separating quick-wins from structural fixes.
5. Remediate & Monitor: Track corrective actions and transition from periodic reviews to continuous automated governance monitoring.

# Scoring governance maturity

Once the audit areas are defined, the next step is to score maturity in a way that shows where the program is inconsistent, where it is repeatable and where it is operating with evidence.

A simple five-point maturity scale is often enough:

1. Ad hoc: Policies or controls exist in isolated places, but they are incomplete, informal or heavily manual.
2. Developing: The organization has defined some governance processes, but coverage is uneven and adoption depends on individual teams.
3. Managed: Core policies, ownership roles and control mechanisms are documented and used consistently for important domains.
4. Measured: Governance performance is tracked through metrics, exceptions are reviewed and leadership can see where controls are weak or incomplete.
5. Optimized: Monitoring is continuous, control coverage is broad, remediation is timely and the program improves through regular feedback rather than one-off cleanup efforts.

# Reference
https://www.snowflake.com/en/data-governance/policy/audit/
