"""Neo4j graph seeding module for the Legislation RAG Platform.

Seeds the knowledge graph with legislation entities, sections, and relationships.
All operations use MERGE for idempotency — safe to run multiple times.

Usage:
    python -m scripts.seed_graph --neo4j-uri bolt://localhost:7687
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog
from neo4j import AsyncGraphDatabase

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Schema: Constraint indexes
# ---------------------------------------------------------------------------

CONSTRAINT_QUERIES = [
    "CREATE CONSTRAINT legislation_title IF NOT EXISTS FOR (l:Legislation) REQUIRE l.title IS UNIQUE",
    "CREATE CONSTRAINT section_id IF NOT EXISTS FOR (s:Section) REQUIRE s.section_id IS UNIQUE",
    "CREATE CONSTRAINT topic_name IF NOT EXISTS FOR (t:Topic) REQUIRE t.name IS UNIQUE",
    "CREATE CONSTRAINT jurisdiction_name IF NOT EXISTS FOR (j:Jurisdiction) REQUIRE j.name IS UNIQUE",
]


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

JURISDICTIONS = [
    {"name": "Commonwealth", "country": "Australia"},
    {"name": "Victoria", "country": "Australia"},
    {"name": "Queensland", "country": "Australia"},
    {"name": "New South Wales", "country": "Australia"},
]

LEGISLATION = [
    {
        "title": "Road Safety Act 2024",
        "year": 2024,
        "number": 42,
        "jurisdiction": "Victoria",
        "status": "in_force",
        "commencement_date": "2025-07-01",
        "subject_matter": "Road safety and driver licensing",
    },
    {
        "title": "Privacy Act 2024",
        "year": 2024,
        "number": 15,
        "jurisdiction": "Commonwealth",
        "status": "in_force",
        "commencement_date": "2024-06-15",
        "subject_matter": "Privacy and personal information protection",
    },
    {
        "title": "Workplace Health and Safety Act 2024",
        "year": 2024,
        "number": 28,
        "jurisdiction": "Queensland",
        "status": "in_force",
        "commencement_date": "2025-01-01",
        "subject_matter": "Workplace health and safety",
    },
]

SECTIONS = [
    # Road Safety Act
    {"section_id": "rsa2024_s1", "number": "1", "title": "Short title", "part": "Part 1", "division": "Division 1", "legislation": "Road Safety Act 2024"},
    {"section_id": "rsa2024_s4", "number": "4", "title": "Definitions", "part": "Part 1", "division": "Division 1", "legislation": "Road Safety Act 2024"},
    {"section_id": "rsa2024_s5", "number": "5", "title": "Application of Act", "part": "Part 1", "division": "Division 2", "legislation": "Road Safety Act 2024"},
    {"section_id": "rsa2024_s7", "number": "7", "title": "Conditions of learner permit", "part": "Part 2", "division": "Division 1", "legislation": "Road Safety Act 2024"},
    {"section_id": "rsa2024_s11", "number": "11", "title": "Driving while exceeding prescribed BAC", "part": "Part 3", "division": "Division 1", "legislation": "Road Safety Act 2024"},
    {"section_id": "rsa2024_s15", "number": "15", "title": "Registration of automated driving system", "part": "Part 4", "division": None, "legislation": "Road Safety Act 2024"},
    {"section_id": "rsa2024_s16", "number": "16", "title": "Duties of automated driving system entity", "part": "Part 4", "division": None, "legislation": "Road Safety Act 2024"},
    {"section_id": "rsa2024_s19", "number": "19", "title": "Compulsory third party insurance", "part": "Part 6", "division": None, "legislation": "Road Safety Act 2024"},
    {"section_id": "rsa2024_s22", "number": "22", "title": "Demerit points", "part": "Part 7", "division": None, "legislation": "Road Safety Act 2024"},
    {"section_id": "rsa2024_s23", "number": "23", "title": "Licence suspension and cancellation", "part": "Part 7", "division": None, "legislation": "Road Safety Act 2024"},
    # Privacy Act
    {"section_id": "pa2024_s6", "number": "6", "title": "APP 3: Collection of solicited personal information", "part": "Part 2", "division": "Division 1", "legislation": "Privacy Act 2024"},
    {"section_id": "pa2024_s10", "number": "10", "title": "APP 8: Cross-border disclosure", "part": "Part 2", "division": "Division 3", "legislation": "Privacy Act 2024"},
    {"section_id": "pa2024_s13", "number": "13", "title": "Meaning of data breach", "part": "Part 3", "division": None, "legislation": "Privacy Act 2024"},
    {"section_id": "pa2024_s14", "number": "14", "title": "Meaning of eligible data breach", "part": "Part 3", "division": None, "legislation": "Privacy Act 2024"},
    {"section_id": "pa2024_s15", "number": "15", "title": "Duty to notify Commissioner", "part": "Part 3", "division": None, "legislation": "Privacy Act 2024"},
    {"section_id": "pa2024_s16", "number": "16", "title": "Duty to notify affected individuals", "part": "Part 3", "division": None, "legislation": "Privacy Act 2024"},
    {"section_id": "pa2024_s17", "number": "17", "title": "Civil penalty provisions", "part": "Part 4", "division": None, "legislation": "Privacy Act 2024"},
    # WHS Act
    {"section_id": "whs2024_s5", "number": "5", "title": "Primary duty of care", "part": "Part 2", "division": "Division 1", "legislation": "Workplace Health and Safety Act 2024"},
    {"section_id": "whs2024_s7", "number": "7", "title": "Duty to manage risks", "part": "Part 2", "division": "Division 1", "legislation": "Workplace Health and Safety Act 2024"},
    {"section_id": "whs2024_s8", "number": "8", "title": "Duty of officers", "part": "Part 2", "division": "Division 2", "legislation": "Workplace Health and Safety Act 2024"},
    {"section_id": "whs2024_s10", "number": "10", "title": "Duty to consult workers", "part": "Part 3", "division": "Division 1", "legislation": "Workplace Health and Safety Act 2024"},
    {"section_id": "whs2024_s14", "number": "14", "title": "Meaning of notifiable incident", "part": "Part 4", "division": None, "legislation": "Workplace Health and Safety Act 2024"},
    {"section_id": "whs2024_s17", "number": "17", "title": "Duty to notify regulator", "part": "Part 4", "division": None, "legislation": "Workplace Health and Safety Act 2024"},
    {"section_id": "whs2024_s20", "number": "20", "title": "Category 1 offences", "part": "Part 7", "division": None, "legislation": "Workplace Health and Safety Act 2024"},
]

TOPICS = [
    {"name": "Road Safety", "parent": None},
    {"name": "Driver Licensing", "parent": "Road Safety"},
    {"name": "Drink Driving", "parent": "Road Safety"},
    {"name": "Automated Vehicles", "parent": "Road Safety"},
    {"name": "Privacy", "parent": None},
    {"name": "Data Breach Notification", "parent": "Privacy"},
    {"name": "Cross-border Disclosure", "parent": "Privacy"},
    {"name": "Australian Privacy Principles", "parent": "Privacy"},
    {"name": "Workplace Health and Safety", "parent": None},
    {"name": "PCBU Duties", "parent": "Workplace Health and Safety"},
    {"name": "Worker Consultation", "parent": "Workplace Health and Safety"},
    {"name": "Notifiable Incidents", "parent": "Workplace Health and Safety"},
]

# Cross-references between legislation
REFERENCES = [
    {"from_section": "rsa2024_s5", "to_legislation": "Privacy Act 2024", "reference_type": "REFERENCES"},
    {"from_section": "rsa2024_s16", "to_legislation": "Workplace Health and Safety Act 2024", "reference_type": "REFERENCES"},
    {"from_section": "rsa2024_s22", "to_section": "rsa2024_s23", "reference_type": "REFERENCES"},
    {"from_section": "rsa2024_s15", "to_section": "rsa2024_s19", "reference_type": "REFERENCES"},
    {"from_section": "pa2024_s16", "to_section": "pa2024_s14", "reference_type": "REFERENCES"},
    {"from_section": "whs2024_s5", "to_legislation": "Road Safety Act 2024", "reference_type": "REFERENCES"},
]

LEGISLATION_TOPIC_MAP = [
    {"legislation": "Road Safety Act 2024", "topic": "Road Safety"},
    {"legislation": "Road Safety Act 2024", "topic": "Driver Licensing"},
    {"legislation": "Road Safety Act 2024", "topic": "Drink Driving"},
    {"legislation": "Road Safety Act 2024", "topic": "Automated Vehicles"},
    {"legislation": "Privacy Act 2024", "topic": "Privacy"},
    {"legislation": "Privacy Act 2024", "topic": "Data Breach Notification"},
    {"legislation": "Privacy Act 2024", "topic": "Cross-border Disclosure"},
    {"legislation": "Privacy Act 2024", "topic": "Australian Privacy Principles"},
    {"legislation": "Workplace Health and Safety Act 2024", "topic": "Workplace Health and Safety"},
    {"legislation": "Workplace Health and Safety Act 2024", "topic": "PCBU Duties"},
    {"legislation": "Workplace Health and Safety Act 2024", "topic": "Worker Consultation"},
    {"legislation": "Workplace Health and Safety Act 2024", "topic": "Notifiable Incidents"},
]


# ---------------------------------------------------------------------------
# Graph seeding operations
# ---------------------------------------------------------------------------


async def create_constraints(session) -> None:
    """Create uniqueness constraint indexes."""
    for query in CONSTRAINT_QUERIES:
        await session.run(query)
    logger.info("seed_graph.constraints.created", count=len(CONSTRAINT_QUERIES))


async def seed_jurisdictions(session) -> None:
    """Seed jurisdiction nodes."""
    query = """
    UNWIND $jurisdictions AS j
    MERGE (jurisdiction:Jurisdiction {name: j.name})
    SET jurisdiction.country = j.country
    """
    await session.run(query, jurisdictions=JURISDICTIONS)
    logger.info("seed_graph.jurisdictions.seeded", count=len(JURISDICTIONS))


async def seed_legislation(session) -> None:
    """Seed legislation nodes and link to jurisdictions."""
    query = """
    UNWIND $legislation AS leg
    MERGE (l:Legislation {title: leg.title})
    SET l.year = leg.year,
        l.number = leg.number,
        l.status = leg.status,
        l.commencement_date = leg.commencement_date,
        l.subject_matter = leg.subject_matter
    WITH l, leg
    MATCH (j:Jurisdiction {name: leg.jurisdiction})
    MERGE (l)-[:ENACTED_IN]->(j)
    """
    await session.run(query, legislation=LEGISLATION)
    logger.info("seed_graph.legislation.seeded", count=len(LEGISLATION))


async def seed_sections(session) -> None:
    """Seed section nodes and link to parent legislation."""
    query = """
    UNWIND $sections AS sec
    MERGE (s:Section {section_id: sec.section_id})
    SET s.number = sec.number,
        s.title = sec.title,
        s.part = sec.part,
        s.division = sec.division
    WITH s, sec
    MATCH (l:Legislation {title: sec.legislation})
    MERGE (s)-[:PART_OF]->(l)
    """
    await session.run(query, sections=SECTIONS)
    logger.info("seed_graph.sections.seeded", count=len(SECTIONS))


async def seed_topics(session) -> None:
    """Seed topic taxonomy nodes and parent-child relationships."""
    # Create all topic nodes
    create_query = """
    UNWIND $topics AS t
    MERGE (topic:Topic {name: t.name})
    """
    await session.run(create_query, topics=TOPICS)

    # Create parent-child relationships
    parent_query = """
    UNWIND $topics AS t
    WITH t WHERE t.parent IS NOT NULL
    MATCH (child:Topic {name: t.name})
    MATCH (parent:Topic {name: t.parent})
    MERGE (child)-[:SUBTOPIC_OF]->(parent)
    """
    await session.run(parent_query, topics=TOPICS)
    logger.info("seed_graph.topics.seeded", count=len(TOPICS))


async def seed_legislation_topics(session) -> None:
    """Link legislation to topics."""
    query = """
    UNWIND $mappings AS m
    MATCH (l:Legislation {title: m.legislation})
    MATCH (t:Topic {name: m.topic})
    MERGE (l)-[:COVERS_TOPIC]->(t)
    """
    await session.run(query, mappings=LEGISLATION_TOPIC_MAP)
    logger.info("seed_graph.legislation_topics.linked", count=len(LEGISLATION_TOPIC_MAP))


async def seed_references(session) -> None:
    """Seed cross-reference relationships between sections and legislation."""
    # Section-to-section references
    section_refs = [r for r in REFERENCES if "to_section" in r]
    if section_refs:
        query = """
        UNWIND $refs AS r
        MATCH (from:Section {section_id: r.from_section})
        MATCH (to:Section {section_id: r.to_section})
        MERGE (from)-[:REFERENCES]->(to)
        """
        await session.run(query, refs=section_refs)

    # Section-to-legislation references
    leg_refs = [r for r in REFERENCES if "to_legislation" in r]
    if leg_refs:
        query = """
        UNWIND $refs AS r
        MATCH (from:Section {section_id: r.from_section})
        MATCH (to:Legislation {title: r.to_legislation})
        MERGE (from)-[:REFERENCES]->(to)
        """
        await session.run(query, refs=leg_refs)

    logger.info("seed_graph.references.seeded", count=len(REFERENCES))


# ---------------------------------------------------------------------------
# Main execution
# ---------------------------------------------------------------------------


async def seed_graph(
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
    dry_run: bool = False,
) -> None:
    """Run the full graph seeding pipeline."""
    logger.info(
        "seed_graph.start",
        neo4j_uri=neo4j_uri,
        dry_run=dry_run,
    )

    if dry_run:
        logger.info("seed_graph.dry_run.jurisdictions", items=[j["name"] for j in JURISDICTIONS])
        logger.info("seed_graph.dry_run.legislation", items=[l["title"] for l in LEGISLATION])
        logger.info("seed_graph.dry_run.sections", count=len(SECTIONS))
        logger.info("seed_graph.dry_run.topics", items=[t["name"] for t in TOPICS])
        logger.info("seed_graph.dry_run.references", count=len(REFERENCES))
        logger.info("seed_graph.dry_run.complete", message="No changes made")
        return

    driver = AsyncGraphDatabase.driver(
        neo4j_uri,
        auth=(neo4j_user, neo4j_password),
    )

    try:
        async with driver.session() as session:
            await create_constraints(session)
            await seed_jurisdictions(session)
            await seed_legislation(session)
            await seed_sections(session)
            await seed_topics(session)
            await seed_legislation_topics(session)
            await seed_references(session)

        logger.info("seed_graph.complete")
    finally:
        await driver.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Seed Neo4j knowledge graph with legislation entities and relationships.",
    )
    parser.add_argument(
        "--neo4j-uri",
        default="bolt://localhost:7687",
        help="Neo4j Bolt URI (default: bolt://localhost:7687)",
    )
    parser.add_argument(
        "--neo4j-user",
        default="neo4j",
        help="Neo4j username (default: neo4j)",
    )
    parser.add_argument(
        "--neo4j-password",
        default="password",
        help="Neo4j password (default: password)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be seeded without making changes",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Entry point for graph seeding."""
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.dev.ConsoleRenderer(),
        ],
    )
    args = parse_args(argv)
    asyncio.run(
        seed_graph(
            neo4j_uri=args.neo4j_uri,
            neo4j_user=args.neo4j_user,
            neo4j_password=args.neo4j_password,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
