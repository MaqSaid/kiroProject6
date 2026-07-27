---
inclusion: auto
---

# Legal Domain Guide

## Legal Entity Types

The platform models legislation using seven entity types stored as nodes in the knowledge graph:

| Entity Type | Description | Example |
|---|---|---|
| **Act** | Primary legislation passed by Parliament | Transport Infrastructure Act 2024 |
| **Section** | A numbered subdivision within an Act or Regulation | Section 45(2) — Speed limit enforcement |
| **Regulation** | Subordinate legislation made under an Act | Heavy Vehicle Access Regulation 2024 |
| **Definition** | A legally defined term within legislation | "road" means any highway, road, or path |
| **Obligation** | A duty imposed on a person or entity | The licensee must display the permit number |
| **Authority** | A power or permission granted by legislation | The Minister may declare a controlled road |
| **Penalty** | A consequence for contravention of an obligation | Maximum penalty: 50 penalty units |

## Legal Relationship Types

Relationships between legal entities are modeled as directed edges in the knowledge graph:

| Relationship Type | Description | Example |
|---|---|---|
| **CONTAINS** | Parent contains child in hierarchy | Act → Part → Division → Section |
| **DEFINES** | Entity provides a definition | Definitions Section → "road" Definition |
| **AMENDS** | One provision modifies another | 2024 Amendment Act AMENDS 2020 Act Section 12 |
| **REFERENCES** | Cross-reference to another provision | Section 45 REFERENCES Section 12 |
| **IMPLEMENTS** | Regulation implements an Act provision | Regulation 2024 IMPLEMENTS Act Section 100 |
| **IMPOSES** | Provision imposes an obligation | Section 45 IMPOSES "must hold valid licence" |
| **GRANTS_POWER** | Provision grants an authority | Section 80 GRANTS_POWER to Minister |
| **PRESCRIBES_PENALTY** | Provision prescribes a penalty | Section 45(5) PRESCRIBES_PENALTY 50 units |

## Legislative Hierarchy

Documents follow a nested structure:

```
Act (top-level)
└── Part (major division, e.g., "Part 3 — Licensing")
    └── Division (subdivision, e.g., "Division 2 — Heavy Vehicles")
        └── Section (numbered provision, e.g., "Section 45")
            └── Subsection (e.g., "45(2)(a)")
```

Key detection patterns:
- **Act title**: First H1 heading, or text matching `<Title> Act <Year>`
- **Part heading**: Lines matching `Part \d+` or `Part [IVX]+`
- **Division heading**: Lines matching `Division \d+`
- **Section**: Lines matching `Section \d+` or `\d+\.` at line start
- **Subsection**: Parenthetical numbering like `(2)`, `(a)`, `(i)`

## Citation Format

All citations in generated answers follow this format:

```
[Act/Regulation Title], Section [number]([subsection])
```

Examples:
- Transport Infrastructure Act 2024, Section 45(2)
- Heavy Vehicle Access Regulation 2024, Section 12(1)(a)
- Road Use Management Act 2024, Part 3 Division 2

## Cross-Reference Keywords

When these keywords appear in a query, the Retrieval Agent prioritizes graph traversal:

- **AMENDS** — Query about how one provision modifies another
- **REFERENCES** — Query about cross-references between provisions
- **IMPLEMENTS** — Query about how regulations implement Act provisions
- Specific section numbers (e.g., "Section 45", "s.12", "Part 3 Division 2")

## Ubiquitous Language Glossary

| Term | Meaning in This Platform |
|---|---|
| **Ingest** | Upload and process a document through chunking, embedding, and graph extraction |
| **Chunk** | A segment of text from a document, with hierarchy metadata preserved |
| **Traverse** | Walk the knowledge graph following relationships between entities |
| **Fusion** | Combine ranked results from multiple retrieval methods (RRF) |
| **Confidence** | Composite score indicating answer reliability (0.0-1.0) |
| **Fallback** | Response returned when confidence < 0.4, suggesting manual consultation |
| **Hierarchy path** | The legislative position of a chunk, e.g., "Part 3, Division 2, Section 45" |
| **MERGE** | Neo4j idempotent upsert operation — create if not exists, update if exists |
| **Degraded response** | Answer produced with fewer than 3 retrieval methods due to service unavailability |
| **Golden dataset** | 20 curated Q&A pairs used for evaluation against sample documents |
