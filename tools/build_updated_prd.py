from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether, ListFlowable, ListItem
)
from reportlab.pdfbase.pdfmetrics import stringWidth


OUT = "output/pdf/Puchoo_ai_Text_to_SQL_Assistant_PRD_Updated.pdf"

NAVY = colors.HexColor("#17324D")
BLUE = colors.HexColor("#35658C")
MID_BLUE = colors.HexColor("#4F8FCC")
PALE_BLUE = colors.HexColor("#F3F8FC")
LIGHT_BLUE = colors.HexColor("#DCEEFF")
GREEN = colors.HexColor("#4C9A66")
GOLD = colors.HexColor("#C88724")
PURPLE = colors.HexColor("#8964C7")
TEXT = colors.HexColor("#202020")
MUTED = colors.HexColor("#526579")
GRID = colors.HexColor("#D9D9D9")


styles = getSampleStyleSheet()
styles.add(ParagraphStyle(
    name="DocTitle", parent=styles["Title"], fontName="Helvetica-Bold",
    fontSize=18, leading=22, textColor=NAVY, alignment=TA_LEFT, spaceAfter=8,
))
styles.add(ParagraphStyle(
    name="Subtitle", parent=styles["Normal"], fontName="Helvetica",
    fontSize=10.4, leading=14, textColor=MUTED, spaceAfter=16,
))
styles.add(ParagraphStyle(
    name="H1Blue", parent=styles["Heading1"], fontName="Helvetica-Bold",
    fontSize=15, leading=19, textColor=BLUE, spaceBefore=15, spaceAfter=7,
    keepWithNext=True,
))
styles.add(ParagraphStyle(
    name="H2Blue", parent=styles["Heading2"], fontName="Helvetica-Bold",
    fontSize=11.7, leading=15, textColor=BLUE, spaceBefore=9, spaceAfter=4,
    keepWithNext=True,
))
styles.add(ParagraphStyle(
    name="BodyTextPRD", parent=styles["BodyText"], fontName="Helvetica",
    fontSize=9.4, leading=13.0, textColor=TEXT, spaceAfter=6,
))
styles.add(ParagraphStyle(
    name="Small", parent=styles["BodyText"], fontName="Helvetica",
    fontSize=8.2, leading=10.4, textColor=TEXT,
))
styles.add(ParagraphStyle(
    name="SmallBold", parent=styles["BodyText"], fontName="Helvetica-Bold",
    fontSize=8.2, leading=10.4, textColor=TEXT,
))
styles.add(ParagraphStyle(
    name="Flow", parent=styles["BodyText"], fontName="Helvetica-Bold",
    fontSize=9.2, leading=14, textColor=NAVY, spaceAfter=7,
))


def p(text, style="BodyTextPRD"):
    return Paragraph(text, styles[style])


def bullets(items, level=0):
    return ListFlowable(
        [ListItem(p(item), leftIndent=0) for item in items],
        bulletType="bullet", start="circle", bulletFontName="Helvetica",
        bulletFontSize=7, leftIndent=15 + level * 10, bulletIndent=4 + level * 10,
        spaceAfter=5,
    )


def table(headers, rows, widths, font_size=8.1):
    data = [[p(h, "SmallBold") for h in headers]]
    for row in rows:
        data.append([p(str(cell), "Small") for cell in row])
    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.45, GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for r in range(1, len(data)):
        if r % 2 == 0:
            commands.append(("BACKGROUND", (0, r), (-1, r), PALE_BLUE))
    t.setStyle(TableStyle(commands))
    return t


def meta_table():
    rows = [
        ["Student Name(s)", "Kunal Singhi, Kunal Dadlani"],
        ["Roll No(s)", "PST-25-0055, PST-25-0054"],
        ["Year & Section", "[Sem / Year & Section]"],
        ["Project Title (as assigned)", "Puchoo.ai - Secure Multilingual Text-to-SQL Analytics Platform"],
        ["Project Type", "GenAI On-Job Training Project"],
        ["Project Stack", "React JavaScript with JSX, Vite, FastAPI, Python, SQLAlchemy, SQL parser / AST validation, Redis, Claude API, Sarvam AI API"],
        ["Repo", "https://github.com/Kayd-06/Puchoo.ai.git"],
    ]
    return table(["OJT Project Design Template", "Text-to-SQL Assistant - Product Requirements Document"], rows, [2.0*inch, 4.85*inch])


def section(title):
    return p(title, "H1Blue")


def sub(title):
    return p(title, "H2Blue")


def on_page(canvas, doc):
    canvas.saveState()
    page = canvas.getPageNumber()
    if page > 1:
        canvas.setStrokeColor(GRID)
        canvas.setLineWidth(0.45)
        canvas.line(doc.leftMargin, A4[1] - 0.44*inch, A4[0] - doc.rightMargin, A4[1] - 0.44*inch)
        canvas.setFont("Helvetica", 7.6)
        canvas.setFillColor(MUTED)
        canvas.drawString(doc.leftMargin, A4[1] - 0.34*inch, "Puchoo.ai - Text-to-SQL Assistant Product Requirements Document")
        right = f"Page {page}"
        canvas.drawRightString(A4[0] - doc.rightMargin, A4[1] - 0.34*inch, right)
    canvas.setStrokeColor(GRID)
    canvas.line(doc.leftMargin, 0.38*inch, A4[0] - doc.rightMargin, 0.38*inch)
    canvas.setFont("Helvetica", 7.3)
    canvas.setFillColor(MUTED)
    canvas.drawString(doc.leftMargin, 0.24*inch, "Internal - OJT Project Design Template")
    canvas.drawRightString(A4[0] - doc.rightMargin, 0.24*inch, "Updated from approved architecture HLD")
    canvas.restoreState()


def story():
    s = []
    s += [Spacer(1, 0.14*inch), p("Text-to-SQL Assistant - Product Requirements Document", "DocTitle")]
    s += [p("Updated PRD aligned to the Puchoo.ai High-Level Design, version 3.0.0", "Subtitle"), meta_table(), Spacer(1, 0.10*inch)]
    s += [p("Document purpose", "H2Blue"), p(
        "This PRD updates the earlier Text-to-SQL Assistant scope to reflect the approved production-grade architecture. "
        "The user-facing application is now a React JavaScript application built with JSX and Vite. FastAPI is the sole security boundary; the browser never holds secrets or makes direct calls to data stores, LLM providers, identity services, or speech services."
    )]
    s += [p("Architecture alignment summary", "H2Blue"), bullets([
        "React JSX UI is presentation state only and communicates with FastAPI through HTTPS APIs.",
        "FastAPI centrally enforces authentication, CSRF protection, workspace policy, RBAC, source permissions, and orchestration.",
        "SQL is a proposal, not an executable instruction: it is AST-validated, policy-authorized, immutably approved, and executed once as a read-only SELECT.",
        "Results are masked and localized when required; history and audit records are append-only and tenant-scoped.",
    ])]
    s.append(PageBreak())

    s += [section("1. Problem Understanding")]
    s += [sub("1.1 What is the problem statement in your own words?")]
    s += [p("People who need answers from business or institutional databases often cannot retrieve them directly because they do not know SQL. They depend on a technical teammate to write a query, run it, and interpret the output. Puchoo.ai removes that bottleneck by allowing an authorized user to ask a question in plain language or by voice and receive an answer derived from an approved database source.")]
    s += [p("The challenge is not simply SQL generation. A production-ready text-to-SQL platform must prevent cross-workspace data access, disallow data changes, limit what an LLM can infer from a schema, retain an audit trail, and make the safety status visible to the user. The architecture therefore treats FastAPI and its policy layer as the sole trust boundary, while the React client remains a presentation layer.")]
    s += [sub("1.2 Why does this problem exist or matter?")]
    s += [p("Databases are optimized for structured querying, not everyday language. Without a guarded natural-language layer:")]
    s += [bullets([
        "Non-technical stakeholders wait on technical staff for routine information requests.",
        "A browser client or unguarded AI integration could expose secret keys, bypass access checks, or query the wrong tenant's data.",
        "AI-generated SQL could be overly broad, reference unsupported objects, or attempt a modifying operation.",
        "Users cannot assess whether the system understood their question unless SQL, guardrail outcome, and verification status are visible.",
        "Voice input requires language handling without turning speech content into authorization evidence or secret-bearing client state.",
    ])]
    s += [p("The project demonstrates a practical pattern for allowing AI-assisted analytics without weakening database, workspace, or audit controls.")]
    s += [sub("1.3 Key Inputs and Expected Outputs")]
    s += [p("Inputs - what the user gives or what the system receives", "H2Blue")]
    s += [bullets([
        "An authenticated personal or institution user session, resolved to a workspace and role.",
        "A selected, authorized data source and its scoped schema catalog, glossary, and source permissions.",
        "A typed question or audio recording. Audio is uploaded only to FastAPI for language processing.",
        "Provider credentials held only as server-side secret references; they are never exposed to React or stored in browser state.",
    ])]
    s += [p("Processes - what the system does internally", "H2Blue")]
    s += [bullets([
        "FastAPI authenticates the request, applies CSRF and workspace policy, and resolves RBAC and source permissions.",
        "Sarvam processing detects, transcribes, translates, or transliterates voice input when required, producing natural-language text only.",
        "The schema catalog provides the least necessary, authorized compact schema context to the Claude provider adapter.",
        "The adapter requests one SQL proposal; guardrails validate its AST, permitted objects, query shape, and limits before creating an immutable approval.",
        "Only the approved read-only SELECT is executed against the customer database. The result worker masks or localizes data as needed and writes append-only audit and history records.",
    ])]
    s += [p("Expected outputs - what the system returns", "H2Blue")]
    s += [bullets([
        "A React view showing the question or transcript, generated SQL proposal, authorization outcome, approved results, and clear status.",
        "A plain-language explanation or confidence / advisory state, without claiming unsupported schema facts.",
        "A visible reason for access denial, validation failure, provider failure, or blocked SQL; no query runs on those paths.",
        "Tenant-scoped query history and audit evidence for authorized members only.",
    ])]
    s += [section("2. Functional Scope")]
    s += [sub("2.1 What are the core features you plan to build?")]
    s += [bullets([
        "React JavaScript with JSX and Vite web application for question entry, audio capture, generated SQL, result tables, history, and status feedback.",
        "CDN, WAF, and TLS edge layer for static application delivery, DDoS reduction, and rate controls.",
        "FastAPI BFF and API gateway providing authentication, CSRF defenses, orchestration, and the only trusted API path.",
        "Identity, session, workspace, and policy service with OIDC integration, RBAC, membership, and source permissions.",
        "Personal and institution workspaces with strict tenant scoping for metadata, query history, audits, and results.",
        "Secure voice recorder that uploads audio only to FastAPI; Sarvam adapter support for STT, detection, translation, and transliteration.",
        "Schema catalog and source registry with compact scoped schema, glossary context, and secret references only.",
        "Claude provider adapter: Sonnet for a SQL proposal and Haiku for advisory / explanation work; inference only.",
        "SQL guardrail and query authorization layer using AST validation, object policy, read-only enforcement, and limits.",
        "Immutable proposal, approval, and one-time read-only execution; result, history, audit, masking, localization, and worker processing.",
    ])]
    s += [sub("2.2 App flow / pipeline")]
    s += [p("User browser -> CDN / WAF / TLS -> React JSX application -> FastAPI BFF / API Gateway -> Identity, Session, Workspace & Policy. Typed questions travel through FastAPI; audio travels from the voice recorder to FastAPI only. The language adapter turns supported speech into canonical text. The schema catalog supplies authorized compact context to the Claude provider adapter, which returns a single SQL proposal. Guardrails authorize the proposal before an immutable approval permits exactly one read-only SELECT. Results are processed for masking, localization, history, and append-only audit before the React UI displays them.", "Flow")]
    s += [sub("2.3 Which libraries or tools will you use?")]
    stack_rows = [
        ["Frontend", "React JavaScript with JSX; Vite; browser presentation state only"],
        ["Backend", "Python and FastAPI BFF / API Gateway"],
        ["Identity and policy", "OIDC identity provider; workspace membership, RBAC, and source permissions"],
        ["Databases", "Customer database through a read-only connection; tenant-scoped metadata database"],
        ["Schema reading", "SQLAlchemy / scoped schema catalog and source registry"],
        ["SQL safety", "AST validation, object policy, read-only enforcement, limits, and immutable approval"],
        ["LLM", "Claude API through a server-side provider adapter; Sonnet proposal and Haiku advisory"],
        ["Speech and language", "Sarvam AI API through a server-side language adapter"],
        ["Infrastructure", "CDN / WAF / TLS, Redis cache / queue, encrypted TTL object storage, secrets manager"],
    ]
    s += [table(["Layer", "Approved design choice"], stack_rows, [1.58*inch, 5.27*inch])]
    s.append(PageBreak())

    s += [section("3. System and Design Thinking")]
    s += [sub("3.1 Architecture decisions that shape the product")]
    arch_rows = [
        ["React is presentation only", "UI state cannot contain secrets or act as authorization truth. The client calls FastAPI over HTTPS only."],
        ["FastAPI is the sole security boundary", "Authentication, CSRF, orchestration, workspace resolution, and authorization are server-side and consistent."],
        ["Tenant-scoped policy", "Membership, role, source permissions, metadata, history, and audit records are scoped to the active workspace."],
        ["SQL is a proposal", "Claude produces one proposal. The system does not execute raw model output or let the browser execute it."],
        ["Approval before execution", "AST validation, object policy, read-only checks, and limits lead to an immutable approval for one SELECT."],
        ["Results are governed artifacts", "The worker can mask and localize results and writes history and append-only audit evidence."],
    ]
    s += [table(["Design principle", "Product implication"], arch_rows, [1.78*inch, 5.07*inch])]
    s += [sub("3.2 Which algorithms or logic are central to this project?")]
    s += [bullets([
        "Scoped schema construction: table, column, relationship, glossary, and source context are reduced to the least necessary authorized prompt context.",
        "Language routing: the server accepts voice input, runs Sarvam speech / language processing as needed, and passes canonical text into the question pipeline.",
        "Prompt construction: the provider adapter combines canonical question text with the approved compact schema and policy-compatible instructions.",
        "AST validation and object policy: SQL is structurally inspected and checked against the allowed statement type, workspace source, object set, limits, and complexity rules.",
        "Immutable approval token: execution uses a validated proposal / approval record rather than an untrusted string re-submitted by the client.",
        "Result governance: masking and localization happen before presentation; audit events are append-only and tenant-scoped.",
    ])]
    s += [sub("3.3 How will you test correctness or performance?")]
    s += [bullets([
        "Unit tests for AST validation, write-operation blocking, allowed-object checks, enforced limits, and immutable approval behavior.",
        "Authorization tests proving a user cannot access another workspace's source, schema, history, audit record, or result.",
        "API tests confirming React receives no provider credentials, database connections, authorization truth, or direct provider paths.",
        "Known-question tests that compare expected query intent with generated proposals and successful read-only results.",
        "Voice tests covering representative Indian languages, transcription errors, translation / transliteration, and failed audio uploads.",
        "Audit, masking, and localization tests using protected sample fields and tenant-separated records.",
        "Performance checks for cache behavior, queue / worker recovery, response time, and repeated request handling under rate controls.",
    ])]
    s.append(PageBreak())

    s += [section("4. Timeline and Milestones 3 Months")]
    timeline = [
        ["Week 1", "Foundation", "Set up repository, React JSX / Vite app, FastAPI service, sample read-only customer DB, metadata model", "Working local architecture baseline"],
        ["Week 2", "Identity and tenancy", "Implement OIDC integration model, workspace resolution, RBAC, membership, and source permissions", "Tenant-aware session and policy path"],
        ["Week 3", "Schema catalog", "Build source registry and scoped schema / glossary catalog through approved read-only metadata access", "Authorized schema-context module"],
        ["Week 4", "React UI v1", "Build question form, source selection, SQL / status panels, results table, and voice-recorder shell", "Functional React presentation UI"],
        ["Week 5", "FastAPI gateway", "Add authenticated HTTPS endpoints, CSRF handling, request orchestration, and rate-control integration points", "Trusted BFF path"],
        ["Week 6", "Language processing", "Add FastAPI audio upload path and Sarvam adapter for STT, detection, translation, and transliteration", "Canonical text from supported voice input"],
        ["Week 7", "Claude proposal", "Implement provider adapter, compact-schema prompt, one SQL proposal, and advisory explanation path", "Server-side SQL proposal flow"],
        ["Week 8", "Guardrails and approval", "Implement AST validation, object policy, limits, immutable approval, and read-only execution", "One approved SELECT execution path"],
        ["Week 9", "Results and audit", "Add masking, localization, tenant-scoped history, append-only audit, Redis queue / locks, and encrypted artifacts", "Governed result lifecycle"],
        ["Week 10", "Security and test suite", "Run isolation, secret-exposure, malicious-query, and failure-path tests", "Security evidence and defect log"],
        ["Week 11", "Polish and resilience", "Tune UX, cache / queue behavior, error messages, metrics, and demo data", "Reliable evaluator-ready experience"],
        ["Week 12", "Documentation and demo", "Finalize README, environment guidance, architecture explanation, test results, and live walkthrough", "Complete demo-ready project"],
    ]
    s += [table(["Week", "Focus Area", "Planned Deliverables", "Output"], timeline, [0.64*inch, 1.24*inch, 3.22*inch, 1.75*inch], 7.5)]
    s.append(PageBreak())

    s += [section("5. Risks and Dependencies")]
    s += [sub("5.1 What is the hardest part technically for you right now?")]
    s += [bullets([
        "Maintaining a strict distinction between browser presentation state and server-side authorization truth.",
        "Defining AST and object-policy checks that are safe, explainable, and usable for legitimate analytical SELECT queries.",
        "Keeping schema context compact enough for reliable model use while ensuring it never includes an unauthorized source or object.",
        "Making approval immutable and execution one-time so the query actually run is the query that was validated.",
        "Handling multilingual voice input and provider failures without confusing transcription quality with access or safety status.",
        "Applying tenant isolation consistently to caches, queues, object storage artifacts, history, and audit records.",
    ])]
    s += [sub("5.2 What dependencies or help do you need from mentors?")]
    s += [bullets([
        "Review of the policy model for workspace membership, RBAC, source permissions, and audit retention.",
        "Feedback on AST validation rules, query limits, and test cases for adversarial model output.",
        "Guidance on safe sample data and a read-only customer-database integration for the demonstration.",
        "Review of React information architecture so proposal, approval, result, and failure states remain understandable.",
        "Advice on provider evaluation, latency, retries, and user-facing handling for Claude and Sarvam failures.",
    ])]
    s += [section("6. End Users and Target Users")]
    s += [p("The Text-to-SQL Assistant is designed for:")]
    s += [bullets([
        "Non-technical business or institute members who need answers from authorized data without writing SQL.",
        "Institution administrators who manage membership and controlled data sources for their workspace.",
        "Students and educators who need a transparent reference implementation of a secure AI analytics workflow.",
        "Developers and reviewers who need a demonstrable separation between UI, policy, model inference, data access, and auditing.",
    ])]
    s += [p("User roles", "H2Blue"), bullets([
        "Question Asker: submits typed or voice questions and views transcript, proposal, approval status, result, and explanation.",
        "Institution Workspace Admin: manages membership, roles, authorized sources, and policy-bound access within an institution.",
        "Platform / Data Administrator: registers sources, manages secret references, observes audits, and configures operational controls without exposing credentials to users.",
    ])]
    s.append(PageBreak())

    s += [section("7. Evaluation Readiness")]
    s += [sub("7.1 How will you prove that your project works?")]
    s += [bullets([
        "Live demo: authenticate as an authorized member, select an approved source, ask a question, and show the React UI's SQL proposal, approval state, results, and audit-aware status.",
        "Security demo: show that React uses FastAPI only, has no provider secrets, and cannot call customer data, identity, Claude, or Sarvam services directly.",
        "Isolation demo: show that a member of one institution cannot retrieve another institution's schema, history, metadata, artifacts, or results.",
        "Guardrail demo: submit a destructive or unauthorized request and show AST / object-policy denial before any database execution.",
        "Read-only demo: show an approved query execution path that permits exactly one SELECT and records the governed outcome.",
        "Voice demo: record supported voice input, show server-side transcription / canonicalization, and continue through the same policy pipeline.",
        "GitHub repository, architecture diagram, automated test evidence, and a recorded project walkthrough.",
    ])]
    s += [sub("7.2 What success metric or goal will you aim for?")]
    s += [bullets([
        "100 percent of requests pass through FastAPI for authentication, authorization, provider access, and database orchestration.",
        "100 percent of modifying SQL and unauthorized object references are rejected before execution in the test suite.",
        "Every successful execution is tied to an immutable approved proposal and uses one read-only SELECT.",
        "Cross-workspace access attempts fail for sources, schema, results, history, audit records, cached data, and artifacts.",
        "The React UI clearly distinguishes proposal, approval, execution, result, and failure states without exposing secrets.",
        "Reasonable response time for a small-to-medium sample dataset in a live demonstration, including clear failure messages when a provider is unavailable.",
    ])]
    s += [section("8. Product Overview")]
    s += [sub("8.1 Product Goal")]
    s += [p("Build a secure multilingual text-to-SQL analytics platform that converts authorized plain-language or voice questions into policy-approved, read-only SQL and returns transparent, governed results. The product must keep authorization and secrets server-side, preserve tenant isolation, never execute unvalidated model output, and retain a useful audit trail.")]
    s += [sub("8.2 Feature Priorities")]
    priorities = [
        ["React JSX / Vite presentation UI with HTTPS FastAPI integration", "Must"],
        ["FastAPI security boundary, authentication, CSRF, workspace policy, RBAC", "Must"],
        ["Authorized source registry and compact scoped schema catalog", "Must"],
        ["Claude provider adapter and one SQL proposal", "Must"],
        ["AST validation, object policy, limits, immutable approval, one read-only SELECT", "Must"],
        ["Tenant-scoped results, masking, history, and append-only audit", "Must"],
        ["Sarvam voice processing path", "Should"],
        ["Redis cache / queue and encrypted TTL artifacts", "Should"],
        ["Advanced localization and ambiguity clarification", "Could"],
    ]
    s += [table(["Feature", "Priority"], priorities, [5.68*inch, 1.17*inch])]

    s += [section("8.3 User Stories")]
    stories = [
        ("US-001", "As an authorized member, I want to sign in and enter only my permitted workspace so that I cannot access another organization’s data.", ["FastAPI resolves identity, membership, role, and source permissions before a schema or result is returned.", "The browser has no authorization truth or direct data-store access."]),
        ("US-002", "As a user, I want to type a question in the React app so that I can request analytics without SQL knowledge.", ["The React app sends the question to FastAPI over HTTPS only.", "The UI shows the active source and does not expose secret values."]),
        ("US-003", "As a user, I want to submit supported voice input so that I can ask a question naturally in my language.", ["Audio is uploaded only to FastAPI.", "Sarvam processing produces canonical natural-language text and does not grant any permission."]),
        ("US-004", "As a user, I want to see the proposed SQL and its safety status so that the system is transparent before I trust an answer.", ["The SQL proposal, authorization state, and result / failure state are visible in the UI.", "The UI never implies a query ran when validation or approval failed."]),
        ("US-005", "As a platform owner, I want SQL guardrails and immutable approval so that untrusted model output cannot modify or improperly read customer data.", ["AST validation enforces statement type, permitted objects, and limits before execution.", "Only an approved record can initiate one read-only SELECT."]),
        ("US-006", "As an institution admin, I want history and audit evidence scoped to my workspace so that activity is traceable without leaking across tenants.", ["Result history, audit records, cache keys, and artifacts are workspace-scoped.", "Audit evidence is append-only and results can be masked or localized before presentation."]),
    ]
    for code, statement, criteria in stories:
        s += [p(code, "H2Blue"), p(statement), p("Acceptance criteria", "SmallBold"), bullets(criteria)]
    s += [sub("8.4 Product States")]
    s += [p("SESSION_RESOLVED -> QUESTION_OR_AUDIO_SUBMITTED -> CANONICAL_TEXT_READY -> SCHEMA_SCOPED -> SQL_PROPOSED -> AST_VALIDATED -> POLICY_AUTHORIZED -> APPROVAL_CREATED -> READ_ONLY_QUERY_EXECUTED -> RESULT_GOVERNED -> RESULT_DISPLAYED", "Flow")]
    s += [p("Failure states: AUTHENTICATION_DENIED, WORKSPACE_ACCESS_DENIED, SOURCE_ACCESS_DENIED, TRANSCRIPTION_FAILED, PROVIDER_FAILED, SQL_VALIDATION_BLOCKED, POLICY_DENIED, APPROVAL_INVALID, EXECUTION_FAILED, RESULT_GOVERNANCE_FAILED. A failure is displayed with a reason and does not progress to execution.")]
    s += [sub("8.5 Product Principles")]
    s += [bullets([
        "Server-side trust: React presents state; FastAPI decides access and handles all secrets.",
        "Least privilege: only workspace-authorized sources, compact schema context, and approved objects reach a request.",
        "Read-only by design: model output is a proposal; only one approved SELECT may run.",
        "Transparency before trust: show proposal, approval, outcome, and failure reasons in the UI.",
        "Tenant isolation everywhere: policy, metadata, result history, audits, queues, caches, and artifacts are scoped.",
        "Auditability by default: governed results and meaningful events leave append-only evidence.",
    ])]

    s += [section("9. Responsibilities")]
    s += [p("Note: task ownership below is a suggested split for a two-student team. Adjust the checkmarks to match the final division of work.", "Small")]
    responsibilities = [
        ["React JSX UI and Vite presentation state", "✓", "", "Question, voice, SQL, status, results, and history views"],
        ["FastAPI gateway and policy integration", "", "✓", "Authentication, CSRF, workspace, RBAC, source checks"],
        ["Schema catalog and read-only source registry", "✓", "", "Scoped schema, glossary, and secret references"],
        ["Claude and Sarvam provider adapters", "", "✓", "Server-side inference and language flow"],
        ["SQL guardrails, immutable approval, read-only execution", "✓", "✓", "AST, object policy, limits, and one-SELECT execution"],
        ["Results, audit, testing, tuning, and demo preparation", "✓", "✓", "Masking, localization, history, isolation tests, documentation"],
    ]
    s += [table(["Task", "K.S.", "K.D.", "Mentor Notes"], responsibilities, [2.55*inch, 0.5*inch, 0.5*inch, 3.3*inch])]
    s += [Spacer(1, 0.10*inch), p("Signatures Students: Kunal Singhi, Kunal Dadlani", "BodyTextPRD"), Spacer(1, 0.06*inch)]
    s += [p("Mentor Approval:", "SmallBold"), Spacer(1, 0.08*inch), p("Date:", "SmallBold")]
    return s


def build():
    doc = BaseDocTemplate(
        OUT, pagesize=A4, leftMargin=0.72*inch, rightMargin=0.62*inch,
        topMargin=0.64*inch, bottomMargin=0.58*inch,
        title="Text-to-SQL Assistant Product Requirements Document",
        author="Kunal Singhi and Kunal Dadlani",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    doc.addPageTemplates([PageTemplate(id="prd", frames=[frame], onPage=on_page)])
    doc.build(story())


if __name__ == "__main__":
    build()
