import { Link } from 'react-router-dom';
import { Mark, focusRing } from '../components/landing/ui';

const pages = {
  privacy: {
    title: 'Privacy',
    paragraphs: [
      'Puchoo.ai stores your name, lowercased email, workspace type, and institute name when you create an institute workspace. Passwords are stored only as an argon2 hash. Session tokens are random and stored only as a hash.',
      'The browser keeps the session in an HttpOnly cookie. React does not store tokens in localStorage and holds no secrets.',
      'An append-only audit log is designed to record each request, the generated SQL, the approval, and the result. Results are masked by policy, and history is kept per workspace.',
    ],
  },
  terms: {
    title: 'Terms',
    paragraphs: [
      'Puchoo.ai is a college OJT project. It proposes SQL for a question you ask, shows that SQL with a plain-language explanation, and waits for your approval.',
      'FastAPI is the only security boundary. An AST-based guardrail allows one SELECT statement, limits queries to approved tables and columns, and enforces row limits and timeouts. If those checks fail, the query does not run.',
    ],
  },
};

export default function Legal({ kind }) {
  const page = pages[kind];
  return (
    <div className="site min-h-screen bg-[#F9FAFB] text-[#111827]">
      <title>{page.title} · Puchoo.ai</title>
      <header className="px-5 py-5 md:px-10">
        <Link
          to="/"
          className={`inline-flex items-center gap-2 font-medium tracking-[-0.03em] ${focusRing} rounded-full`}
        >
          <Mark className="h-6 w-6" />
          Puchoo.ai
        </Link>
      </header>
      <main className="mx-auto max-w-2xl px-5 py-12 md:px-10">
        <h1 className="text-[40px] font-medium tracking-[-0.03em] md:text-[48px]">{page.title}</h1>
        <div className="mt-8 space-y-5 text-[17px] leading-relaxed text-[#6B7280]">
          {page.paragraphs.map((paragraph) => (
            <p key={paragraph}>{paragraph}</p>
          ))}
        </div>
      </main>
    </div>
  );
}
