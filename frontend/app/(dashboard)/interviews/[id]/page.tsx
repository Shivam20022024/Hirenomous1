'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft, Loader2, Check, X, HelpCircle, FileText, RefreshCw, MessageSquare, Video, Play, TrendingUp, AlertTriangle } from 'lucide-react';
import { fetchApi } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { StatusPill } from '@/components/status-pill';

const scoreColor = (v: number) =>
  v >= 80 ? 'text-success' : v >= 60 ? 'text-primary' : v >= 40 ? 'text-warning-text' : 'text-destructive';
const barColor = (v: number) =>
  v >= 80 ? 'bg-success' : v >= 60 ? 'bg-primary' : v >= 40 ? 'bg-warning' : 'bg-destructive';

const REC_LABEL: Record<string, string> = {
  strong_match: 'STRONG MATCH',
  match: 'MATCH',
  weak_match: 'WEAK MATCH',
  no_match: 'NO MATCH',
};

const DIMENSIONS: [string, string][] = [
  ['technical_knowledge', 'Technical Knowledge'],
  ['problem_solving', 'Problem Solving'],
  ['communication', 'Communication'],
  ['role_specific', 'Role-specific Skills'],
  ['experience', 'Experience'],
  ['answer_relevance', 'Answer Relevance'],
];

export default function InterviewReportPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id as string;
  const router = useRouter();

  const [report, setReport] = useState<any>(null);
  const [detail, setDetail] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [transcript, setTranscript] = useState<any[] | null>(null);
  const [showTranscript, setShowTranscript] = useState(false);
  const [recording, setRecording] = useState<{ url: string; title: string } | null>(null);
  const [recLoading, setRecLoading] = useState<number | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const [r, d] = await Promise.all([
        fetchApi(`/interviews/${id}/report`),
        fetchApi(`/interviews/${id}`).catch(() => null),
      ]);
      setReport(r);
      setDetail(d);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const viewRecording = async (answerIndex: number, title: string) => {
    setRecLoading(answerIndex);
    try {
      const blob = await fetchApi(`/interviews/${id}/recording/${answerIndex}`);
      setRecording({ url: URL.createObjectURL(blob as Blob), title });
    } catch (err: any) {
      alert(err.message || 'Recording not available.');
    } finally {
      setRecLoading(null);
    }
  };

  const closeRecording = () => {
    if (recording) URL.revokeObjectURL(recording.url);
    setRecording(null);
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const openTranscript = async () => {
    setShowTranscript(true);
    if (transcript) return;
    try {
      const t = await fetchApi(`/interviews/${id}/transcript`);
      setTranscript(t.transcript || []);
    } catch (err: any) {
      alert(err.message);
    }
  };

  const reevaluate = async () => {
    setBusy(true);
    try {
      await fetchApi(`/interviews/${id}/reevaluate`, { method: 'POST' });
      await load();
    } catch (err: any) {
      alert(err.message);
    } finally {
      setBusy(false);
    }
  };

  const decide = async (decision: 'select' | 'reject' | 'needs_review') => {
    const labels: Record<string, string> = { select: 'select', reject: 'reject', needs_review: 'mark for human review' };
    if (!confirm(`Are you sure you want to ${labels[decision]} this candidate?`)) return;
    setBusy(true);
    try {
      const res = await fetchApi(`/interviews/${id}/decision`, {
        method: 'POST',
        body: JSON.stringify({ decision }),
      });
      if (decision === 'select' || decision === 'reject') {
        const em = res?.decision_email ?? res?.selection_email;
        const what = decision === 'select' ? 'selected' : 'rejected';
        const mail = decision === 'select' ? 'selection email' : 'rejection email';
        alert(em?.sent
          ? `Candidate ${what} — ${mail} sent.`
          : `Candidate ${what}. ${mail[0].toUpperCase() + mail.slice(1)} not sent (${em?.errors?.[0] || 'SMTP not configured'}).`);
      }
      await load();
    } catch (err: any) {
      alert(err.message);
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return (
      <div className="p-16 text-center">
        <Loader2 className="mx-auto h-7 w-7 animate-spin text-primary" />
      </div>
    );
  }
  if (!report) {
    return <div className="p-16 text-center text-muted-foreground">Interview not found.</div>;
  }

  const scores = report.scores || {};
  const overall = scores.overall;
  const rec = report.recommendation;
  const aiReport = report.ai_report || {};
  const evaluated = report.evaluation_status === 'evaluated' || report.evaluation_status === 'needs_review';
  const decided = report.recruiter_decision;

  return (
    <div className="mx-auto max-w-[1000px] space-y-6 px-5 py-9 lg:px-8 lg:py-14">
      <Link href="/interviews" className="inline-flex items-center gap-1.5 text-sm font-semibold text-muted-foreground hover:text-primary">
        <ArrowLeft size={16} /> Back to interviews
      </Link>

      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="eyebrow">AI Interview Report</p>
          <h1 className="mt-2 text-4xl font-bold tracking-tight text-foreground">{report.candidate_name}</h1>
          <p className="mt-1.5 text-base font-semibold text-muted-foreground">{report.position}</p>
        </div>
        {report.status === 'completed' ? (
          <StatusPill domain="interview" status="completed" label={String(report.status).replace('_', ' ')} />
        ) : (
          <StatusPill domain="interview" status={report.status} label={String(report.status).replace('_', ' ')} />
        )}
      </div>

      {report.status !== 'completed' ? (
        <div className="rounded-xl border border-dashed border-border p-10 text-center text-base font-semibold text-foreground">
          This interview has not been completed yet, so there is no report to show.
        </div>
      ) : !evaluated ? (
        <div className="rounded-xl border border-border bg-card p-8 text-center">
          <p className="text-base font-semibold text-foreground">
            The interview is complete but the AI evaluation has not finished (status: {report.evaluation_status}).
          </p>
          <Button onClick={reevaluate} disabled={busy} className="mt-4">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw size={14} />} Run evaluation
          </Button>
        </div>
      ) : (
        <>
          {/* Overall + recommendation */}
          <div className="grid gap-4 sm:grid-cols-[1fr_1.4fr]">
            <div className="rounded-xl border border-border bg-card p-7">
              <p className="text-sm font-bold uppercase tracking-[0.14em] text-muted-foreground">Overall Score</p>
              <p className={`mt-3 font-mono text-6xl font-black tracking-tight ${overall != null ? scoreColor(overall) : 'text-foreground'}`}>
                {overall != null ? Math.round(overall) : '—'}
                <span className="text-2xl font-semibold text-muted-foreground"> / 100</span>
              </p>
              {rec && (
                <span className="mt-5 inline-block">
                  <span className="mr-1.5 text-sm font-bold uppercase tracking-wider text-muted-foreground">AI Recommendation:</span>
                  <StatusPill domain="recommendation" status={rec} label={REC_LABEL[rec] || rec} />
                </span>
              )}
              <p className="mt-4 text-xs font-medium text-muted-foreground">
                Advisory only. The recruiter makes the final decision.
              </p>
            </div>

            <div className="rounded-xl border border-border bg-card p-7">
              <p className="mb-5 text-sm font-bold uppercase tracking-[0.14em] text-muted-foreground">Breakdown</p>
              <div className="space-y-4">
                {DIMENSIONS.map(([key, label]) => {
                  const v = scores[key];
                  return (
                    <div key={key}>
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-semibold text-foreground">{label}</span>
                        <span className={`font-mono text-base font-bold ${v != null ? scoreColor(v) : 'text-muted-foreground'}`}>
                          {v != null ? Math.round(v) : '—'}
                          <span className="text-xs font-medium text-muted-foreground">/100</span>
                        </span>
                      </div>
                      <Progress value={v || 0} className="mt-1.5" barClassName={barColor(v || 0)} />
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Strengths / areas */}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="rounded-xl border border-border bg-card p-6">
              <h3 className="mb-4 flex items-center gap-2 text-base font-bold text-success">
                <TrendingUp size={17} /> Strengths
              </h3>
              <ul className="space-y-2.5 text-sm font-medium text-foreground/80">
                {(aiReport.strengths || []).length ? (
                  aiReport.strengths.map((s: string, i: number) => (
                    <li key={i} className="flex gap-2.5">
                      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-success" />
                      {s}
                    </li>
                  ))
                ) : (
                  <li className="text-muted-foreground/70">None highlighted.</li>
                )}
              </ul>
            </div>
            <div className="rounded-xl border border-border bg-card p-6">
              <h3 className="mb-4 flex items-center gap-2 text-base font-bold text-warning-text">
                <AlertTriangle size={17} /> Areas to Improve
              </h3>
              <ul className="space-y-2.5 text-sm font-medium text-foreground/80">
                {(aiReport.areas_to_improve || []).length ? (
                  aiReport.areas_to_improve.map((s: string, i: number) => (
                    <li key={i} className="flex gap-2.5">
                      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-warning" />
                      {s}
                    </li>
                  ))
                ) : (
                  <li className="text-muted-foreground/70">None highlighted.</li>
                )}
              </ul>
            </div>
          </div>

          {aiReport.summary && (
            <div className="rounded-xl border border-border bg-card p-6">
              <h3 className="mb-3 flex items-center gap-2 text-base font-bold text-foreground">
                <FileText size={17} /> Summary
              </h3>
              <p className="border-l-4 border-primary/40 pl-4 text-[15px] font-medium leading-relaxed text-foreground/90">
                {aiReport.summary}
              </p>
            </div>
          )}

          {/* No recordings on disk (never captured, or purged) — tell the recruiter */}
          {report.status === 'completed'
            && (detail?.answers?.length ?? 0) > 0
            && !detail.answers.some((a: any) => a.has_video || a.has_audio) && (
            <div className="rounded-xl border border-dashed border-border bg-card p-5 text-sm text-muted-foreground">
              <span className="font-bold text-foreground">Answer recordings:</span> none are available for this interview
              (the candidate answered by text, or the video files are no longer stored). The full transcript is still available.
            </div>
          )}

          {/* Answer recordings (recruiter-only, streamed through the authenticated endpoint) */}
          {detail?.answers?.some((a: any) => a.has_video || a.has_audio) && (
            <div className="rounded-xl border border-border bg-card p-6">
              <h3 className="mb-4 flex items-center gap-2 text-base font-bold text-foreground">
                <Video size={17} /> Answer Recordings
              </h3>
              <div className="space-y-2">
                {detail.answers.map((a: any) => {
                  if (!a.has_video && !a.has_audio) return null;
                  const q = (detail.question_plan || []).find((x: any) => x.id === a.question_id);
                  const title = q?.text || `Answer ${a.answer_index + 1}`;
                  return (
                    <div key={a.answer_index} className="flex items-center justify-between gap-3 rounded-lg border border-border bg-background p-3.5">
                      <p className="min-w-0 flex-1 truncate text-sm font-medium text-foreground/80">
                        {q?.is_followup ? 'Follow-up: ' : ''}{title}
                      </p>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => viewRecording(a.answer_index, title)}
                        disabled={recLoading === a.answer_index}
                      >
                        {recLoading === a.answer_index ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
                        {a.has_video ? 'View recording' : 'Play audio'}
                      </Button>
                    </div>
                  );
                })}
              </div>
              <p className="mt-4 text-xs font-medium text-muted-foreground">
                Recordings are for interview review only. AI scoring is based solely on the answer transcript — never on appearance.
              </p>
            </div>
          )}

          {/* Interview meta */}
          <div className="flex flex-wrap items-center gap-10 rounded-xl border border-border bg-card p-6">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Questions</p>
              <p className="mt-1.5 font-mono text-2xl font-bold text-foreground">{report.questions_total}</p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Answered</p>
              <p className="mt-1.5 font-mono text-2xl font-bold text-foreground">{report.questions_answered}</p>
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Duration</p>
              <p className="mt-1.5 font-mono text-2xl font-bold text-foreground">{report.duration_minutes != null ? `${report.duration_minutes} min` : '—'}</p>
            </div>
            {report.evaluation_status === 'needs_review' && (
              <div className="flex items-center gap-1.5 text-sm font-semibold text-warning-text">
                <HelpCircle size={15} /> Flagged for human review (limited interview data)
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-card p-6">
            <Button variant="outline" size="lg" onClick={openTranscript}>
              <MessageSquare size={16} /> View Transcript
            </Button>

            {decided ? (
              <span className="inline-flex items-center gap-2 rounded-xl bg-muted px-4 py-2.5 text-sm font-bold text-muted-foreground">
                Recruiter decision: <span className="uppercase text-foreground">{decided}</span>
                {report.recruiter_feedback ? ` — “${report.recruiter_feedback}”` : ''}
              </span>
            ) : (
              <>
                <Button size="lg" variant="success" onClick={() => decide('select')} disabled={busy}>
                  <Check size={16} /> Select Candidate
                </Button>
                <Button size="lg" variant="destructive" onClick={() => decide('reject')} disabled={busy}>
                  <X size={16} /> Reject Candidate
                </Button>
                <Button size="lg" variant="outline" onClick={() => decide('needs_review')} disabled={busy}>
                  <HelpCircle size={16} /> Needs Review
                </Button>
              </>
            )}
          </div>
          <p className="text-xs font-medium text-muted-foreground">
            Selecting a candidate updates their status and sends the standard selection email. Inviting or
            completing an interview never does this.
          </p>
        </>
      )}

      {/* Recording modal */}
      <Dialog open={!!recording} onOpenChange={(open) => !open && closeRecording()}>
        <DialogContent className="max-w-3xl p-0">
          {recording && (
            <>
              <DialogHeader className="border-b border-border px-6 py-4 mb-0">
                <DialogTitle className="flex items-center gap-2 text-sm"><Video size={16} /> {recording.title}</DialogTitle>
              </DialogHeader>
              <div className="p-4">
                <video src={recording.url} controls autoPlay className="w-full rounded-lg bg-black" />
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>

      {/* Transcript modal */}
      <Dialog open={showTranscript} onOpenChange={setShowTranscript}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-lg"><FileText size={18} /> Interview Transcript</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {transcript === null ? (
              <Loader2 className="mx-auto h-6 w-6 animate-spin text-primary" />
            ) : transcript.length === 0 ? (
              <p className="text-center text-sm text-muted-foreground">No transcript recorded.</p>
            ) : (
              transcript.map((t, i) => (
                <div key={i} className={`flex ${t.role === 'candidate' ? 'justify-end' : 'justify-start'}`}>
                  <div
                    className={`max-w-[80%] rounded-2xl px-4 py-3 text-[15px] leading-relaxed ${
                      t.role === 'candidate'
                        ? 'bg-primary text-primary-foreground rounded-tr-sm'
                        : 'border border-border bg-muted text-foreground rounded-tl-sm'
                    }`}
                  >
                    <p className="mb-1 text-[11px] font-bold uppercase tracking-wider opacity-70">
                      {t.role === 'candidate' ? report.candidate_name : 'AI Interviewer'}
                    </p>
                    {t.text}
                  </div>
                </div>
              ))
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
