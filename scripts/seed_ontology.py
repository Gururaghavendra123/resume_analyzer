"""
Seed the skill ontology graph with ESCO-inspired data.

Run this script to verify the ontology is loaded correctly
and inspect skill implications.

Usage:
    python scripts/seed_ontology.py
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from core.ontology import OntologyGraph


def main():
    """Load and display the ontology graph."""
    ontology = OntologyGraph()
    ontology.load_seed_data()

    print(f"\n{'='*60}")
    print(f"  Skill Ontology Graph")
    print(f"  Nodes: {ontology.graph.number_of_nodes()}")
    print(f"  Edges: {ontology.graph.number_of_edges()}")
    print(f"{'='*60}\n")

    # Show some example inferences
    examples = [
        ("PyTorch", "Python"),
        ("NextJS", "JavaScript"),
        ("Kubernetes", "Docker"),
        ("Helm", "Docker"),  # Transitive: Helm → Kubernetes → Docker
        ("BERT", "Machine Learning"),  # Transitive: BERT → Transformers → Deep Learning → ML
        ("React Native", "JavaScript"),
    ]

    print("  Example Inferences:")
    print(f"  {'-'*56}")
    for known, target in examples:
        implied = ontology.get_implied_skills(known.lower())
        has_path = target.lower() in implied
        status = "✓" if has_path else "✗"
        print(f"  {status}  {known:20s} → {target:20s} {'(yes)' if has_path else '(no)'}")

    print(f"\n  {'─'*56}")
    print(f"\n  What does knowing 'PyTorch' imply?")
    implied = ontology.get_implied_skills("pytorch")
    for skill in sorted(implied):
        print(f"    → {skill}")

    print(f"\n  What implies 'Python'?")
    implying = ontology.get_implying_skills("python")
    for skill in sorted(implying)[:15]:
        print(f"    ← {skill}")
    if len(implying) > 15:
        print(f"    ... and {len(implying) - 15} more")

    print()


if __name__ == "__main__":
    main()
