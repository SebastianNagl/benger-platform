"""
Pseudonym generator for GDPR-compliant user anonymization

Generates unique, friendly pseudonyms following EDPB Guidelines 01/2025.
Pseudonyms use AdjectiveNoun format for memorability while maintaining uniqueness.
"""

import secrets
from typing import Optional, Set

# Curated lists for friendly, professional pseudonyms suitable for legal domain
ADJECTIVES = [
    "Swift",
    "Wise",
    "Bold",
    "Clever",
    "Noble",
    "Keen",
    "Bright",
    "Steady",
    "Sharp",
    "Quick",
    "Fair",
    "Just",
    "True",
    "Clear",
    "Calm",
    "Firm",
    "Sound",
    "Sage",
    "Adept",
    "Astute",
    "Deft",
    "Skilled",
    "Lucid",
    "Able",
    "Alert",
    "Active",
    "Loyal",
    "Earnest",
    "Zealous",
    "Prudent",
    "Diligent",
    "Careful",
    "Thorough",
    "Precise",
    "Exact",
    "Strict",
    "Rigid",
    "Solid",
    "Strong",
    "Secure",
    "Safe",
    "Sober",
    "Modest",
    "Humble",
    "Patient",
    "Gentle",
    "Kind",
    "Warm",
    "Cordial",
    "Polite",
    "Civil",
    "Gracious",
    "Courtly",
    "Refined",
    "Elegant",
    "Poised",
    "Serene",
    "Tranquil",
    "Peaceful",
    "Quiet",
    "Still",
    "Silent",
    "Subtle",
    "Discreet",
]

NOUNS = [
    "Eagle",
    "Scholar",
    "Judge",
    "Advocate",
    "Counselor",
    "Arbiter",
    "Sage",
    "Mentor",
    "Guardian",
    "Keeper",
    "Warden",
    "Steward",
    "Trustee",
    "Curator",
    "Custodian",
    "Sentinel",
    "Defender",
    "Protector",
    "Champion",
    "Patron",
    "Ally",
    "Friend",
    "Colleague",
    "Partner",
    "Associate",
    "Fellow",
    "Peer",
    "Companion",
    "Comrade",
    "Cohort",
    "Aide",
    "Helper",
    "Guide",
    "Navigator",
    "Pioneer",
    "Explorer",
    "Seeker",
    "Finder",
    "Hunter",
    "Tracker",
    "Analyst",
    "Expert",
    "Specialist",
    "Authority",
    "Master",
    "Virtuoso",
    "Adept",
    "Pro",
    "Agent",
    "Envoy",
    "Delegate",
    "Deputy",
    "Representative",
    "Proxy",
    "Emissary",
    "Ambassador",
    "Architect",
    "Builder",
    "Creator",
    "Maker",
    "Crafter",
    "Artisan",
    "Craftsman",
    "Wright",
]


def generate_pseudonym(
    existing_pseudonyms: Optional[Set[str]] = None, max_attempts: int = 100
) -> str:
    """
    Generate a unique, friendly pseudonym in AdjectiveNoun format.

    Uses cryptographically secure random selection to ensure unpredictability
    and compliance with GDPR pseudonymization requirements.

    Args:
        existing_pseudonyms: Set of already-used pseudonyms to avoid collisions
        max_attempts: Maximum retry attempts before raising error

    Returns:
        Unique pseudonym string (e.g., "WiseScholar", "BoldJudge")

    Raises:
        ValueError: If unable to generate unique pseudonym after max_attempts

    Examples:
        >>> pseudonym = generate_pseudonym()
        >>> print(pseudonym)  # e.g., "SwiftEagle"

        >>> existing = {"SwiftEagle", "WiseScholar"}
        >>> pseudonym = generate_pseudonym(existing)
        >>> assert pseudonym not in existing
    """
    existing = existing_pseudonyms or set()

    for attempt in range(max_attempts):
        # Use secrets for cryptographically secure random selection
        adjective = secrets.choice(ADJECTIVES)
        noun = secrets.choice(NOUNS)
        pseudonym = f"{adjective}{noun}"

        if pseudonym not in existing:
            return pseudonym

    # If we exhausted attempts, raise detailed error
    total_combinations = len(ADJECTIVES) * len(NOUNS)
    raise ValueError(
        f"Unable to generate unique pseudonym after {max_attempts} attempts. "
        f"Existing pseudonyms: {len(existing)}, "
        f"Total possible combinations: {total_combinations}. "
        f"Consider expanding the adjective/noun lists."
    )


def assign_pseudonyms_to_existing_users(db) -> int:
    """
    Assign unique pseudonyms to all users that don't have one.

    This function is used during migration to backfill pseudonyms for existing users.
    It ensures all pseudonyms are unique across the database.

    Args:
        db: SQLAlchemy database session

    Returns:
        Number of users that received new pseudonyms

    Raises:
        ValueError: If unable to generate enough unique pseudonyms
    """
    from models import User

    # Get all users without pseudonyms
    users_without_pseudonyms = db.query(User).filter(User.pseudonym.is_(None)).all()

    if not users_without_pseudonyms:
        return 0

    # Get all existing pseudonyms to avoid collisions
    existing_pseudonyms = set(
        row[0] for row in db.query(User.pseudonym).filter(User.pseudonym.isnot(None)).all()
    )

    # Assign pseudonyms to users
    count = 0
    for user in users_without_pseudonyms:
        try:
            user.pseudonym = generate_pseudonym(existing_pseudonyms)
            existing_pseudonyms.add(user.pseudonym)
            count += 1
        except ValueError as e:
            db.rollback()
            raise ValueError(
                f"Failed to assign pseudonym to user {user.id} (#{count + 1}/{len(users_without_pseudonyms)}): {e}"
            )

    db.commit()
    return count


def get_pseudonym_statistics() -> dict:
    """
    Get statistics about the pseudonym generator capacity.

    Returns:
        Dictionary with statistics about available combinations
    """
    total_combinations = len(ADJECTIVES) * len(NOUNS)
    return {
        "adjectives": len(ADJECTIVES),
        "nouns": len(NOUNS),
        "total_combinations": total_combinations,
        "sample_pseudonyms": [generate_pseudonym() for _ in range(5)],
    }


if __name__ == "__main__":
    # Display statistics when run directly
    stats = get_pseudonym_statistics()
    print(f"Pseudonym Generator Statistics:")
    print(f"  Adjectives: {stats['adjectives']}")
    print(f"  Nouns: {stats['nouns']}")
    print(f"  Total Combinations: {stats['total_combinations']:,}")
    print(f"\nSample pseudonyms:")
    for pseudonym in stats['sample_pseudonyms']:
        print(f"  - {pseudonym}")
