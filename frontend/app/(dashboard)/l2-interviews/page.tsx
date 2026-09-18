'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Loader2, Eye, FileText, Send, XCircle, Check, X } from 'lucide-react';
import { fetchApi } from '@/lib/api';
import { PageHeader } from '@/components/page-header';
import { StatusPill } from '@/components/status-pill';
import { Select } from '@/components/ui/select';
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '@/components/ui/table';

const REC_LABEL: Record<string, string> = {
  strong_match: 'Strong match',
  match: 'Match',
  weak_match: 'Weak match',
  no_match: 'No match',
};

export default function InterviewsPage() {
  const [interviews, setInterviews] = useState<any[]>([]);
  const [jobs, setJobs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [jobFilter, setJobFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [recFilter, setRecFilter] = useState('');

  const load = async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams();
      if (jobFilter) qs.set('job_id', jobFilter);
      if (statusFilter) qs.set('status', statusFilter);
      if (recFilter) qs.set('recommendation', recFilter);
      qs.set('interview_type', 'ai_l2_technical');
      const [rows, jobsData] = await Promise.all([
        fetchApi(`/interviews?${qs}`),
        fetchApi('/jobs'),
      ]);
      setInterviews(rows);
      setJobs(jobsData);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobFilter, statusFilter, recFilter]);

  const resend = async (id: string) => {
    setBusyId(id);
    try {
      const res = await fetchApi(`/interviews/${id}/send-invite`, { method: 'POST' });
      alert(res?.invite?.sent ? 'Invitation re-sent.' : `Invite not sent: ${res?.invite?.reason || 'unknown error'}`);
      load();
    } catch (err: any) {
      alert(err.message);
    } finally {
      setBusyId(null);
    }
  };

  const cancel = async (id: string) => {
    if (!confirm('Cancel this interview? The candidate link will stop working.')) return;
    setBusyId(id);
    try {
      await fetchApi(`/interviews/${id}/cancel`, { method: 'POST' });
      load();
    } catch (err: any) {
      alert(err.message);
    } finally {
      setBusyId(null);
    }
  };

  const decide = async (id: string, decision: 'select' | 'reject') => {
    const label = decision === 'select' ? 'select' : 'reject';
    if (!confirm(`Are you sure you want to ${label} this candidate?`)) return;
    setBusyId(id);
    try {
      const res = await fetchApi(`/interviews/${id}/decision`, {
        method: 'POST',
        body: JSON.stringify({ decision }),
      });
      {
        const em = res?.decision_email ?? res?.selection_email;
        const what = decision === 'select' ? 'selected' : 'rejected';
        const mail = decision === 'select' ? 'Selection email' : 'Rejection email';
        alert(em?.sent
          ? `Candidate ${what}. ${mail} sent.`
          : `Candidate ${what}. ${mail} not sent: ${em?.errors?.[0] || 'no email configured'}`);
      }
      load();
    } catch (err: any) {
      alert(err.message);
    } finally {
      setBusyId(null);
    }
  };

  const handleInviteL2 = async (iv: any) => {
    if (!confirm(`Invite candidate to an L2 System Design interview?`)) return;
    setBusyId(iv.id);
    try {
      const res = await fetchApi('/interviews', {
        method: 'POST',
        body: JSON.stringify({ 
          candidate_id: iv.candidate_id, 
          job_id: iv.job_id || null,
          interview_type: 'ai_l2_technical'
        }),
      });
      if (res?.created === false) {
        alert('This candidate already has an active AI interview — no new invite was sent.');
      } else if (res?.invite?.sent) {
        alert('L2 AI interview created and invitation email sent.');
      } else {
        alert(`L2 AI interview created. Invitation email not sent (${res?.invite?.reason || 'no email / SMTP not configured'}). Link: ${res?.interview_url || 'n/a'}`);
      }
      load();
    } catch (err: any) {
      alert(`Failed to create L2 interview: ${err.message}`);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="mx-auto max-w-[1240px] space-y-6 px-5 py-9 lg:px-8 lg:py-14">
      <PageHeader
        eyebrow="Assessments"
        title="L2 AI Interviews"
        description="Review deep-dive system design and advanced technical interviews."
      />

      <div className="flex flex-wrap gap-2">
        <Select value={jobFilter} onChange={(e) => setJobFilter(e.target.value)} className="h-10 w-auto min-w-[160px]">
          <option value="">All jobs</option>
          {jobs.map((j) => (
            <option key={j.id} value={j.id}>{j.title}</option>
          ))}
        </Select>
        <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="h-10 w-auto min-w-[160px]">
          <option value="">All statuses</option>
          {['invited', 'in_progress', 'completed', 'cancelled', 'expired', 'failed'].map((s) => (
            <option key={s} value={s}>{s.replace('_', ' ')}</option>
          ))}
        </Select>
        <Select value={recFilter} onChange={(e) => setRecFilter(e.target.value)} className="h-10 w-auto min-w-[180px]">
          <option value="">All recommendations</option>
          {Object.keys(REC_LABEL).map((r) => (
            <option key={r} value={r}>{REC_LABEL[r]}</option>
          ))}
        </Select>
      </div>

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Candidate</TableHead>
            <TableHead>Position</TableHead>
            <TableHead>Interview Status</TableHead>
            <TableHead>Date</TableHead>
            <TableHead>AI Score</TableHead>
            <TableHead>Recommendation</TableHead>
            <TableHead>Duration</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {loading ? (
            <TableRow>
              <TableCell colSpan={8} className="py-16 text-center">
                <Loader2 className="mx-auto h-6 w-6 animate-spin text-primary" />
              </TableCell>
            </TableRow>
          ) : interviews.length === 0 ? (
            <TableRow>
              <TableCell colSpan={8} className="py-12 text-center text-muted-foreground">
                No interviews yet. Invite an interested candidate from the Candidates page.
              </TableCell>
            </TableRow>
          ) : (
            interviews.map((iv) => (
              <TableRow key={iv.id}>
                <TableCell className="font-medium text-foreground">{iv.candidate_name}</TableCell>
                <TableCell className="text-muted-foreground">{iv.position}</TableCell>
                <TableCell>
                  <StatusPill domain="interview" status={iv.status} label={String(iv.status).replace('_', ' ')} />
                  {iv.status === 'completed' && iv.evaluation_status !== 'evaluated' && (
                    <span className="ml-1 text-[10px] text-muted-foreground">({iv.evaluation_status})</span>
                  )}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {iv.completed_at
                    ? new Date(iv.completed_at).toLocaleDateString()
                    : iv.invited_at
                    ? new Date(iv.invited_at).toLocaleDateString()
                    : new Date(iv.created_at).toLocaleDateString()}
                </TableCell>
                <TableCell className="font-mono font-semibold">
                  {iv.overall_score != null ? `${Math.round(iv.overall_score)}/100` : '—'}
                </TableCell>
                <TableCell>
                  {iv.recommendation ? (
                    <StatusPill domain="recommendation" status={iv.recommendation} label={REC_LABEL[iv.recommendation] || iv.recommendation} />
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {iv.duration_seconds ? `${Math.round(iv.duration_seconds / 60)} min` : '—'}
                </TableCell>
                <TableCell>
                  <div className="flex items-center justify-end gap-1">
                    <Link
                      href={`/l2-interviews/${iv.id}`}
                      className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground hover:bg-primary/10 hover:text-primary"
                      title="View report"
                    >
                      {iv.status === 'completed' ? <FileText size={15} /> : <Eye size={15} />}
                    </Link>
                    {['invited', 'scheduled', 'expired', 'in_progress'].includes(iv.status) && (
                      <button
                        onClick={() => resend(iv.id)}
                        disabled={busyId === iv.id}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground hover:bg-primary/10 hover:text-primary disabled:opacity-40"
                        title="Resend invitation"
                      >
                        <Send size={15} />
                      </button>
                    )}
                    {!['completed', 'cancelled', 'expired', 'failed'].includes(iv.status) && (
                      <button
                        onClick={() => cancel(iv.id)}
                        disabled={busyId === iv.id}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-40"
                        title="Cancel interview"
                      >
                        <XCircle size={15} />
                      </button>
                    )}
                    {iv.status === 'completed' && !iv.recruiter_decision && (
                      <>
                        <button
                          onClick={() => decide(iv.id, 'select')}
                          disabled={busyId === iv.id}
                          className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-success hover:bg-success/10 disabled:opacity-40"
                          title="Select candidate"
                        >
                          <Check size={15} />
                        </button>
                        <button
                          onClick={() => decide(iv.id, 'reject')}
                          disabled={busyId === iv.id}
                          className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-destructive hover:bg-destructive/10 disabled:opacity-40"
                          title="Reject candidate"
                        >
                          <X size={15} />
                        </button>
                      </>
                    )}
                    {iv.recruiter_decision && (
                      <span className="ml-1 text-[10px] font-semibold uppercase text-muted-foreground">
                        {iv.recruiter_decision}
                      </span>
                    )}
                    {iv.recruiter_decision === 'select' && (
                      <button
                        onClick={() => handleInviteL2(iv)}
                        disabled={busyId === iv.id}
                        className="ml-1 inline-flex h-8 w-8 items-center justify-center rounded-lg text-primary hover:bg-primary/10 disabled:opacity-40"
                        title="Invite to L2 Interview"
                      >
                        <Send size={15} />
                      </button>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  );
}
