/**
 * Bare layout for the candidate-facing AI interview.
 * No recruiter sidebar, no auth context usage — the interview token in the URL
 * is the only credential.
 */
export default function InterviewLayout({ children }: { children: React.ReactNode }) {
  return <div className="min-h-screen bg-muted/30">{children}</div>;
}
