"""Handwritten realistic document content for seeding."""

# Reuse similar personas to mock-gmail for cross-environment consistency
PERSONAS = {
    "sarah": {"name": "Sarah Chen", "email": "sarah.chen@nexusai.com", "role": "manager"},
    "marcus": {"name": "Marcus Johnson", "email": "marcus.johnson@nexusai.com", "role": "engineer"},
    "priya": {"name": "Priya Patel", "email": "priya.patel@nexusai.com", "role": "engineer"},
    "tom": {"name": "Tom Wilson", "email": "tom.wilson@nexusai.com", "role": "designer"},
    "elena": {"name": "Elena Rodriguez", "email": "elena.rodriguez@nexusai.com", "role": "pm"},
    "david": {"name": "David Kim", "email": "david.kim@nexusai.com", "role": "data_scientist"},
    "rachel": {"name": "Rachel Green", "email": "rachel.green@nexusai.com", "role": "hr"},
    "alex": {"name": "Alex Thompson", "email": "alex@nexusai.com", "role": "cto"},
    "mom": {"name": "Linda Thompson", "email": "linda.thompson@gmail.com", "role": "personal"},
    "college_friend": {"name": "Jake Morrison", "email": "jake.morrison@gmail.com", "role": "personal"},
}

USER_EMAIL = "alex@nexusai.com"
USER_NAME = "Alex Thompson"

# Documents organized by category
DOCUMENTS = {
    "meeting_notes": [
        {
            "title": "Q1 Sprint Planning Notes",
            "owner": "sarah",
            "days_ago": 15,
            "body": """Q1 Sprint Planning Notes
March 3, 2026

Attendees: Sarah Chen, Marcus Johnson, Priya Patel, Alex Thompson

Agenda:
1. Review Q4 retrospective items
2. Capacity planning for Q1
3. Priority stack ranking

Key Decisions:
- Moving to two-week sprints (was three-week)
- Alex to own the API v2 migration
- Marcus takes lead on performance optimization
- Priya handles the new auth middleware

Action Items:
- [ ] Alex: Draft API v2 migration plan by March 10
- [ ] Marcus: Set up performance benchmarks by March 7
- [ ] Priya: Review auth middleware RFC by March 5
- [ ] Sarah: Update roadmap in Notion by March 6

Capacity:
- Alex: 80% (20% on-call rotation)
- Marcus: 100%
- Priya: 90% (10% interviewing)

Next meeting: March 17, 2026
""",
        },
        {
            "title": "Weekly Standup - March 10",
            "owner": "sarah",
            "days_ago": 8,
            "body": """Weekly Standup - March 10, 2026

Updates:
- Alex: API v2 migration plan draft is 60% done, found some backward compat issues
- Marcus: Performance benchmarks running, seeing 2x improvement on read path
- Priya: Auth middleware RFC reviewed, left comments for Elena

Blockers:
- Need decision on whether to support v1 API alongside v2
- CI pipeline flaky on integration tests (Marcus looking into it)

Parking Lot:
- Discuss hiring plan for Q2 (Rachel to schedule)
""",
        },
        {
            "title": "Product Review Meeting",
            "owner": "elena",
            "days_ago": 5,
            "body": """Product Review Meeting
March 13, 2026

Presenter: Elena Rodriguez
Attendees: Alex, Sarah, Tom, David

Demo:
- New dashboard UI (Tom's design)
- Real-time analytics pipeline (David's work)

Feedback:
- Dashboard looks great, but needs dark mode toggle
- Analytics latency is 2.3s avg, target is <1s
- Consider adding export to CSV for reports

Decisions:
- Ship dashboard beta to internal users by March 20
- David to optimize analytics query path
- Tom to add dark mode in next sprint

Customer feedback highlights:
- 3 enterprise customers asked for SSO integration
- Performance complaints from 2 accounts with >100k records
""",
        },
        {
            "title": "1:1 Notes - Alex & Sarah",
            "owner": "{user}",
            "days_ago": 3,
            "body": """1:1 Notes - Alex & Sarah
March 15, 2026

Topics discussed:
- Team morale is good, Marcus appreciated the shoutout last week
- Priya might be interested in tech lead track
- Budget for Q2 cloud spend needs review

My notes:
- Need to be more proactive about giving feedback
- Sarah suggested I mentor the new junior engineer starting in April
- Consider blocking off Friday afternoons for deep work
""",
        },
        {
            "title": "Incident Postmortem - March 8",
            "owner": "marcus",
            "days_ago": 10,
            "body": """Incident Postmortem - March 8, 2026

Severity: P2
Duration: 47 minutes
Impact: API latency spike affecting 12% of requests

Timeline:
14:23 - PagerDuty alert fires for p95 latency > 5s
14:28 - Marcus acknowledges, begins investigation
14:35 - Root cause identified: connection pool exhaustion on read replica
14:42 - Temporary fix: increased pool size from 50 to 100
14:51 - Metrics normalize
15:10 - Incident closed

Root Cause:
A new batch job (deployed that morning) was holding long-running transactions
on the read replica, exhausting the connection pool.

Action Items:
- [ ] Marcus: Add connection pool monitoring dashboard
- [ ] Alex: Review batch job deployment process
- [ ] Priya: Add circuit breaker for read replica connections
""",
        },
    ],
    "specs": [
        {
            "title": "API v2 Migration Plan",
            "owner": "{user}",
            "days_ago": 7,
            "body": """API v2 Migration Plan
Author: Alex Thompson
Last updated: March 11, 2026

Overview:
This document outlines the migration strategy from API v1 to v2.
The migration must be backward compatible for at least 6 months.

Breaking Changes in v2:
1. Pagination now uses cursor-based instead of offset
2. Dates are ISO 8601 (was Unix timestamps)
3. Error responses follow RFC 7807 Problem Details
4. Authentication requires OAuth 2.0 (was API key)

Migration Phases:
Phase 1 (March): Core endpoints — /users, /documents, /search
Phase 2 (April): Webhook endpoints and event schemas
Phase 3 (May): Deprecation notices for v1, migration tooling
Phase 4 (June): v1 sunset for new integrations

Risks:
- 47 active integrations on v1, 12 are enterprise accounts
- Some integrations use undocumented v1 quirks
- Mobile SDK needs update for cursor pagination

Dependencies:
- Auth service OAuth 2.0 support (Elena's team, ETA March 20)
- API gateway rate limit changes (DevOps, ETA March 15)
""",
        },
        {
            "title": "Mobile App Architecture",
            "owner": "tom",
            "days_ago": 20,
            "body": """Mobile App Architecture
Author: Tom Wilson
Status: Draft

Tech Stack:
- React Native 0.73
- TypeScript
- Zustand for state management
- React Query for API caching

Architecture:
- Feature-based folder structure
- Shared UI components in /components
- API layer abstracted behind repository pattern
- Offline-first with SQLite local cache

Key Screens:
1. Dashboard - summary cards, recent activity
2. Documents - list, search, filter
3. Editor - rich text editing with collaboration
4. Settings - user preferences, notifications

Performance Targets:
- Cold start: <2s
- Screen transitions: <300ms
- API response caching: 5min TTL for reads
""",
        },
        {
            "title": "Data Pipeline Redesign",
            "owner": "david",
            "days_ago": 12,
            "body": """Data Pipeline Redesign
Author: David Kim
Date: March 6, 2026

Problem:
Current ETL pipeline processes data in hourly batches, leading to
stale dashboards and delayed alerting.

Proposed Solution:
Move to streaming architecture using Kafka + Flink.

Architecture:
Source DBs -> CDC (Debezium) -> Kafka -> Flink -> Data Lake -> BI Tools

Benefits:
- Real-time data freshness (seconds vs hours)
- Better backpressure handling
- Exactly-once processing guarantees

Timeline:
- March: POC with one data source
- April: Production deployment for core tables
- May: Full migration, decommission batch pipeline

Cost Estimate:
- Kafka cluster: $2,400/month
- Flink cluster: $1,800/month
- Total: $4,200/month (vs current $1,200/month for batch)
- ROI: faster insights justify 3.5x cost increase

Risks:
- Team has limited Kafka experience
- Schema evolution needs careful planning
""",
        },
    ],
    "personal": [
        {
            "title": "Reading List 2026",
            "owner": "{user}",
            "days_ago": 45,
            "body": """Reading List 2026

Currently Reading:
- "Designing Data-Intensive Applications" by Martin Kleppmann (Chapter 7)

To Read:
- "Staff Engineer" by Will Larson
- "The Manager's Path" by Camille Fournier
- "System Design Interview Vol 2" by Alex Xu
- "Thinking in Systems" by Donella Meadows

Completed:
- "An Elegant Puzzle" by Will Larson (Jan - loved it)
- "Build" by Tony Fadell (Feb - good stories but repetitive)
""",
        },
        {
            "title": "Trip Planning - Japan",
            "owner": "{user}",
            "days_ago": 30,
            "body": """Trip Planning - Japan (May 2026)

Dates: May 10-24

Itinerary:
Days 1-4: Tokyo (Shibuya, Akihabara, Tsukiji, TeamLab)
Days 5-7: Hakone (ryokan, hot springs, Owakudani)
Days 8-10: Kyoto (temples, Fushimi Inari, Arashiyama)
Days 11-12: Osaka (street food, Dotonbori, day trip to Nara)
Days 13-14: Tokyo (shopping, departure)

Budget:
- Flights: $1,200 (booked)
- Hotels: ~$2,000
- JR Pass: $350
- Food/Activities: ~$1,500
- Total: ~$5,050

To Do:
- [ ] Book hotels (need to decide on ryokan)
- [ ] Get JR Pass
- [ ] Download offline maps
- [ ] Learn basic Japanese phrases
- [ ] Check if passport needs renewal
""",
        },
        {
            "title": "Recipe Collection",
            "owner": "{user}",
            "days_ago": 60,
            "body": """Recipe Collection

== Weeknight Dinners ==

Garlic Butter Pasta:
- Cook 400g spaghetti al dente
- Sautee 6 cloves garlic in 4 tbsp butter
- Add red pepper flakes, pasta water
- Toss with pasta, top with parmesan

Sheet Pan Chicken:
- Season chicken thighs with paprika, garlic powder, salt
- Toss broccoli and sweet potatoes with olive oil
- 425F for 25 min

== Weekend Projects ==

Homemade Ramen:
- Tare: soy sauce + mirin + dashi
- Broth: pork bones, 6 hour simmer
- Toppings: chashu, soft egg, nori, scallion
""",
        },
    ],
    "shared": [
        {
            "title": "Company Handbook",
            "owner": "rachel",
            "days_ago": 90,
            "body": """NexusAI Company Handbook
Last updated: December 2025

Mission:
Build AI tools that make knowledge work more productive and enjoyable.

Values:
1. Ship fast, learn faster
2. Default to transparency
3. Own your outcomes
4. Lift others up

Time Off:
- Unlimited PTO (minimum 15 days/year)
- Company-wide shutdown: Dec 23 - Jan 1
- Sick days: no cap, no questions asked

Remote Work:
- Fully remote, with optional NYC and SF offices
- Core hours: 10am-3pm PT for synchronous work
- $1,000/year home office stipend

Benefits:
- Health/dental/vision (100% company paid)
- 401k with 4% match
- $2,500/year learning budget
- Monthly wellness stipend: $100
""",
        },
        {
            "title": "Onboarding Checklist",
            "owner": "rachel",
            "days_ago": 60,
            "body": """New Employee Onboarding Checklist

Week 1:
- [ ] Set up laptop and accounts (IT ticket)
- [ ] Complete HR paperwork in BambooHR
- [ ] Read Company Handbook
- [ ] 1:1 with manager
- [ ] Meet your onboarding buddy
- [ ] Join #general, #engineering, #random on Slack

Week 2:
- [ ] Complete security training
- [ ] Set up dev environment (see Engineering Wiki)
- [ ] First PR (fix a good-first-issue)
- [ ] Shadow a support rotation

Week 3-4:
- [ ] Take on first feature ticket
- [ ] Attend sprint planning
- [ ] Schedule 1:1s with cross-functional partners
""",
        },
        {
            "title": "Engineering Style Guide",
            "owner": "marcus",
            "days_ago": 40,
            "body": """Engineering Style Guide

Python:
- Black for formatting (line length 100)
- Ruff for linting
- Type hints required for public functions
- Docstrings: Google style

TypeScript:
- Prettier + ESLint
- Strict mode enabled
- Prefer const over let
- No any unless justified in comment

Git:
- Branch naming: feat/, fix/, chore/
- Commit messages: imperative mood, <72 chars
- Squash merge to main
- PR reviews: 1 approval minimum, 2 for infra changes

Testing:
- Unit tests for business logic
- Integration tests for API endpoints
- E2E tests for critical user flows
- Coverage target: 80% for new code
""",
        },
    ],
    "templates": [
        {
            "title": "1:1 Meeting Template",
            "owner": "{user}",
            "days_ago": 50,
            "body": """1:1 Meeting Template

Date: [DATE]
With: [NAME]

How are you doing? (personal check-in)


What's going well?


What's challenging?


Feedback for me?


Action items:
- [ ]
- [ ]
""",
        },
        {
            "title": "Project Proposal Template",
            "owner": "elena",
            "days_ago": 55,
            "body": """Project Proposal Template

Project Name: [NAME]
Author: [AUTHOR]
Date: [DATE]

Problem Statement:
What problem are we solving? Who is affected?

Proposed Solution:
High-level description of the approach.

Success Metrics:
How will we measure success?

Timeline:
Phase 1:
Phase 2:
Phase 3:

Resources Needed:
- Engineering:
- Design:
- Other:

Risks and Mitigations:

Open Questions:
""",
        },
    ],
}

# Flat list for easy iteration
ALL_DOCUMENTS = []
for category, docs in DOCUMENTS.items():
    for doc in docs:
        ALL_DOCUMENTS.append({**doc, "category": category})
