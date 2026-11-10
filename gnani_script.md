# Puchoo.si — Video Script

**Event:** Great Indian AI Internship Challenge
**Team:** Kunal Dadlani and Kunal Singhi

| Speaker | Part |
|---|---|
| Kunal Dadlani | Introduction, product demo, and Gnani AI voice features |
| Kunal Singhi | Security, team roles, and closing |

---

## Part 1 — Kunal Dadlani (Start)

### Introduction

Hello everyone! I'm Kunal Dadlani, and together with my teammate Kunal Singhi, we built Puchoo.si for the Great Indian AI Internship Challenge. Our idea is simple: people should be able to understand their data without knowing SQL. Puchoo.si lets users upload Excel or CSV files, or connect PostgreSQL and MySQL databases, and ask questions in everyday language.

### Product demo

Let me show you how it works. After connecting our data, we can ask, "Which product had the highest sales last month?" Puchoo.si interprets the question and generates a SQL query for us to review. Once we approve it, the system runs the query and presents the results with a clear explanation. Users can also download CSV and PDF reports to share their findings.

### Gnani AI voice features

A key highlight is our integration of Gnani AI's speech-to-text and text-to-speech models. Speech-to-text converts spoken questions into text, while text-to-speech allows users to listen to answers. This brings voice into the analytics experience and makes interacting with data more accessible.

### Handover

Now, Kunal Singhi will explain the security features and how different team members can collaborate.

---

## Part 2 — Kunal Singhi (Continue and End)

### Security

Thank you, Kunal Dadlani! I'm Kunal Singhi. Puchoo.si follows a clear workflow: ask, review, run, and verify. Queries require user approval before execution, and our SQL guardrails allow validated, read-only queries while blocking operations that modify data or access restricted resources. We also use query timeouts, result limits, password hashing, email OTP verification during login, and protected sessions to support secure access.

### Team collaboration

For team collaboration, we support three roles: Viewer, Editor, and Admin.

- **Viewers** can review workspace history.
- **Editors** can ask questions, inspect the data schema, review SQL, and execute approved queries.
- **Admins** can additionally upload files, manage database connections, and control member access.

These permissions are enforced by the backend, while workspace isolation helps keep each team's information separate.

### Closing

By combining these security controls with Gnani AI-powered speech-to-text and text-to-speech, Puchoo.si makes data exploration more conversational while keeping users in control. Our goal is to help people move from a simple question to a useful insight without technical barriers.

We're Kunal Dadlani and Kunal Singhi, and this is Puchoo.si for the Great Indian AI Internship Challenge — ask your data, review the query, and hear the answer. Thank you!

---

> **Note:** This is the script as recorded for the challenge video. The app has since changed: questions now run automatically through the read-only SQL guardrails after you press Enter, with no separate approval step, and vague questions get a quick follow-up with choice buttons.
