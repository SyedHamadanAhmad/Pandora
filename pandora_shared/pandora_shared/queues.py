"""RabbitMQ queue names — must match Tech Spec v1.7 §2.4 and §15.2."""

# Input parsing
PARSE_TEXT = "pandora.parse.text"
PARSE_IMAGE = "pandora.parse.image"
PARSE_URL = "pandora.parse.url"
PARSE_RESULTS = "pandora.parse.results"

# Brief and schema (work / result split — same pattern as parse.text → parse.results)
BRIEF_REQUEST = "pandora.brief.request"
BRIEF_READY = "pandora.brief.ready"
SCHEMA_REQUEST = "pandora.schema.request"
SCHEMA_READY = "pandora.schema.ready"

# Component generation and feedback
COMPONENT_GENERATE = "pandora.component.generate"
COMPONENT_GENERATED = "pandora.component.generated"
COMPONENT_VALIDATED = "pandora.component.validated"
COMPONENT_FAILED = "pandora.component.failed"

# Verification
VERIFICATION_START = "pandora.verification.start"
VERIFICATION_REVISIONS = "pandora.verification.revisions"
VERIFICATION_COMPLETE = "pandora.verification.complete"

# Showcase
SHOWCASE_GENERATE = "pandora.showcase.generate"
SHOWCASE_READY = "pandora.showcase.ready"

# Frontend SSE relay
FRONTEND_EVENTS = "pandora.frontend.events"

ALL_QUEUES: list[str] = [
    PARSE_TEXT,
    PARSE_IMAGE,
    PARSE_URL,
    PARSE_RESULTS,
    BRIEF_REQUEST,
    BRIEF_READY,
    SCHEMA_REQUEST,
    SCHEMA_READY,
    COMPONENT_GENERATE,
    COMPONENT_GENERATED,
    COMPONENT_VALIDATED,
    COMPONENT_FAILED,
    VERIFICATION_START,
    VERIFICATION_REVISIONS,
    VERIFICATION_COMPLETE,
    SHOWCASE_GENERATE,
    SHOWCASE_READY,
    FRONTEND_EVENTS,
]
