"""Folder hierarchy definitions for seed data.

Defines the folder tree structure for a realistic startup Google Drive.
Persona: Alex Chen, founder/CEO of NexusAI (same persona as mock-gmail).
"""

# Each entry: (name, children)
# Children can be nested tuples for sub-folders or None for leaf folders.

FOLDER_TREE = {
    "Engineering": {
        "Backend": {
            "API Docs": None,
            "Architecture": None,
            "Runbooks": None,
        },
        "Frontend": {
            "Design Assets": None,
            "Component Docs": None,
        },
        "Infrastructure": {
            "Terraform": None,
            "Monitoring": None,
        },
        "Sprint Planning": None,
        "Interviews": None,
        "old": None,
    },
    "Product": {
        "PRDs": None,
        "Roadmaps": None,
        "User Research": {
            "Interview Notes": None,
            "Survey Results": None,
        },
        "Design Specs": None,
        "Competitive Analysis": None,
    },
    "Finance": {
        "Budgets": None,
        "Invoices": None,
        "Financial Models": None,
        "Tax": None,
        "Vendor Contracts": None,
    },
    "HR": {
        "Policies": None,
        "Hiring": {
            "Job Descriptions": None,
            "Interview Scorecards": None,
        },
        "Onboarding": None,
        "Performance Reviews": None,
    },
    "Legal": {
        "Contracts": None,
        "IP": None,
        "Compliance": None,
        "NDAs": None,
    },
    "Marketing": {
        "Brand Assets": None,
        "Blog Drafts": None,
        "Campaigns": None,
        "Pitch Decks": None,
        "Social Media": None,
    },
    "Shared": {
        "All Hands": None,
        "Templates": None,
        "Team Photos": None,
        "Vendor Reports": None,
    },
    "tmp": None,
}

# Users for the seed
USERS = [
    {"id": "user_alex", "email": "alex@nexusai.com", "display_name": "Alex Chen"},
    {"id": "user_jordan", "email": "jordan@nexusai.com", "display_name": "Jordan Kim"},
    {"id": "user_priya", "email": "priya@nexusai.com", "display_name": "Priya Sharma"},
    {"id": "user_marcus", "email": "marcus@nexusai.com", "display_name": "Marcus Thompson"},
    {"id": "user_sarah", "email": "sarah@nexusai.com", "display_name": "Sarah Lin"},
    {"id": "user_investor", "email": "david@sequoia.com", "display_name": "David Park"},
    {"id": "user_vendor", "email": "support@dataflow.io", "display_name": "DataFlow Support"},
]
