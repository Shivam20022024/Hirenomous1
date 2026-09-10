'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams } from 'next/navigation';
import {
  Video, VideoOff, Mic, MicOff, Volume2, Wifi, Loader2, CheckCircle2, AlertCircle,
  Play, Square, RefreshCw, Circle, Keyboard,
} from 'lucide-react';
import { interviewApi } from '@/lib/interview-api';

type Phase = 'loading' | 'error' | 'complete' | 'device-check' | 'interview';
type MediaState = 'idle' | 'requesting' | 'granted' | 'denied' | 'unavailable' | 'unsupported';

interface SessionInfo {
  candidate_first_name: string;
  job_title: string;
  status: string;
  mode?: string;
  total_questions: number;
  answered_questions?: number;
  in_progress?: boolean;
  already_completed: boolean;
  assesses: string[];
}
interface QuestionPayload {
  done: boolean;
  question_text?: string;
  is_followup?: boolean;
  question_number?: number;
  total_questions?: number;
  audio_file?: string | null;
  message?: string;
}

const VIDEO_MIME = ['video/webm;codecs=vp9,opus', 'video/webm;codecs=vp8,opus', 'video/webm', 'video/mp4'];
const AUDIO_MIME = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg'];
const pickMime = (list: string[]) =>
  typeof MediaRecorder !== 'undefined'
    ? list.find((t) => { try { return MediaRecorder.isTypeSupported(t); } catch { return false; } })
    : undefined;

export default function CandidateVideoInterviewPage() {
  const params = useParams<{ token: string }>();
  const token = params?.token as string;

  const [phase, setPhase] = useState<Phase>('loading');
  const [errorMsg, setErrorMsg] = useState('');
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [question, setQuestion] = useState<QuestionPayload | null>(null);

  const [media, setMedia] = useState<MediaState>('idle');
  const [camOn, setCamOn] = useState(false);
  const [micOn, setMicOn] = useState(false);
  const [speakerOk, setSpeakerOk] = useState(true);
  const [online, setOnline] = useState(true);

  const [recording, setRecording] = useState(false);
  const [recSeconds, setRecSeconds] = useState(0);
  const [processing, setProcessing] = useState(false);
  const [aiSpeaking, setAiSpeaking] = useState(false);
  const [turnError, setTurnError] = useState('');
  const [useTextFallback, setUseTextFallback] = useState(false);
  const [textAnswer, setTextAnswer] = useState('');
  const [completeMessage, setCompleteMessage] = useState('');

  const streamRef = useRef<MediaStream | null>(null);
  const videoElRef = useRef<HTMLVideoElement | null>(null);
  const vRecRef = useRef<MediaRecorder | null>(null);
  const aRecRef = useRef<MediaRecorder | null>(null);
  const vChunks = useRef<Blob[]>([]);
  const aChunks = useRef<Blob[]>([]);
  const pendingVideo = useRef<Blob | null>(null);
  const pendingAudio = useRef<Blob | null>(null);
  const pendingDuration = useRef<number>(0);
  const timerRef = useRef<any>(null);
  const aiAudioRef = useRef<HTMLAudioElement | null>(null);

  // ---- load session ----
  useEffect(() => {
    if (!token) return;
    (async () => {
      try {
        const info: SessionInfo = await interviewApi.getSession(token);
        setSession(info);
        if (info.already_completed || info.status === 'completed') {
          setCompleteMessage('This interview has already been completed. Thank you.');
          setPhase('complete');
        } else {
          setPhase('device-check');
        }
      } catch (err: any) {
        setErrorMsg(err?.message || 'This interview link is not valid.');
        setPhase('error');
      }
    })();
  }, [token]);

  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    setOnline(navigator.onLine);
    window.addEventListener('online', on);
    window.addEventListener('offline', off);
    return () => { window.removeEventListener('online', on); window.removeEventListener('offline', off); };
  }, []);

  const stopStream = useCallback(() => {
    try { if (vRecRef.current?.state === 'recording') vRecRef.current.stop(); } catch {}
    try { if (aRecRef.current?.state === 'recording') aRecRef.current.stop(); } catch {}
    if (timerRef.current) clearInterval(timerRef.current);
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);
  useEffect(() => () => stopStream(), [stopStream]);

  // ---- camera + mic ----
  const requestMedia = async (): Promise<boolean> => {
    if (typeof MediaRecorder === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      setMedia('unsupported');
      return false;
    }
    setMedia('requesting');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      streamRef.current = stream;
      setCamOn(stream.getVideoTracks().some((t) => t.enabled && t.readyState === 'live'));
      setMicOn(stream.getAudioTracks().some((t) => t.enabled && t.readyState === 'live'));
      stream.getVideoTracks()[0]?.addEventListener('ended', () => setCamOn(false));
      stream.getAudioTracks()[0]?.addEventListener('ended', () => setMicOn(false));
      try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        setSpeakerOk(devices.some((d) => d.kind === 'audiooutput'));
      } catch {}
      setMedia('granted');
      return true;
    } catch (e: any) {
      setMedia(e?.name === 'NotFoundError' || e?.name === 'DevicesNotFoundError' ? 'unavailable' : 'denied');
      return false;
    }
  };

  // attach stream to <video> whenever we have both
  useEffect(() => {
    if (videoElRef.current && streamRef.current && media === 'granted') {
      videoElRef.current.srcObject = streamRef.current;
      videoElRef.current.play().catch(() => {});
    }
  }, [media, phase]);

  // ---- AI question audio ----
  const playQuestionAudio = useCallback(async (q: QuestionPayload) => {
    if (!q.audio_file) return;
    try {
      setAiSpeaking(true);
      const audio = new Audio(interviewApi.audioUrl(token, q.audio_file));
      aiAudioRef.current = audio;
      await audio.play();
      await new Promise<void>((resolve) => {
        audio.onended = () => resolve();
        audio.onerror = () => resolve();
      });
    } catch {
      /* autoplay blocked — the question text is always visible */
    } finally {
      setAiSpeaking(false);
    }
  }, [token]);

  const replayAudio = () => { if (question?.audio_file) playQuestionAudio(question); };

  // ---- start / resume ----
  const startInterview = async () => {
    let ok = !!streamRef.current;
    if (!ok) ok = await requestMedia();
    try {
      setProcessing(true);
      setTurnError('');
      const q: QuestionPayload = await interviewApi.start(token);
      setProcessing(false);
      setPhase('interview');
      if (q.done) { await finishInterview(); return; }
      setQuestion(q);
      if (!ok) setUseTextFallback(true);
      playQuestionAudio(q);
    } catch (err: any) {
      setProcessing(false);
      if (err?.status === 410) { setErrorMsg(err.message); setPhase('error'); }
      else { setTurnError(err?.message || 'Could not start the interview. Please retry.'); }
    }
  };

  // ---- recording (dual: video for review + audio for STT) ----
  const beginRecording = () => {
    if (!streamRef.current) { setUseTextFallback(true); return; }
    vChunks.current = []; aChunks.current = [];
    setRecSeconds(0);
    try {
      const vType = pickMime(VIDEO_MIME);
      const aType = pickMime(AUDIO_MIME);
      const vRec = new MediaRecorder(streamRef.current, vType ? { mimeType: vType } : undefined);
      vRec.ondataavailable = (e) => e.data.size > 0 && vChunks.current.push(e.data);
      vRecRef.current = vRec;

      const audioOnly = new MediaStream(streamRef.current.getAudioTracks());
      const aRec = new MediaRecorder(audioOnly, aType ? { mimeType: aType } : undefined);
      aRec.ondataavailable = (e) => e.data.size > 0 && aChunks.current.push(e.data);
      aRecRef.current = aRec;

      vRec.start();
      aRec.start();
      setRecording(true);
      timerRef.current = setInterval(() => setRecSeconds((s) => s + 1), 1000);
    } catch {
      setUseTextFallback(true);
    }
  };

  const stopAndSubmit = async () => {
    if (timerRef.current) clearInterval(timerRef.current);
    const finalize = (rec: MediaRecorder | null, chunks: Blob[]): Promise<Blob | null> =>
      new Promise((resolve) => {
        if (!rec || rec.state !== 'recording') return resolve(null);
        rec.onstop = () => resolve(new Blob(chunks, { type: chunks[0]?.type || rec.mimeType || 'video/webm' }));
        rec.stop();
      });
    const [vBlob, aBlob] = await Promise.all([
      finalize(vRecRef.current, vChunks.current),
      finalize(aRecRef.current, aChunks.current),
    ]);
    pendingVideo.current = vBlob;
    pendingAudio.current = aBlob;
    pendingDuration.current = recSeconds;
    setRecording(false);
    await submitTurn();
  };

  const submitTextAnswer = async () => {
    if (!textAnswer.trim()) return;
    pendingVideo.current = null;
    pendingAudio.current = null;
    await submitTurn(textAnswer.trim());
    setTextAnswer('');
  };

  const submitTurn = async (answerText?: string) => {
    setProcessing(true);
    setTurnError('');
    try {
      const next: QuestionPayload = await interviewApi.turn(token, {
        video: pendingVideo.current || undefined,
        audio: pendingAudio.current || undefined,
        answerText,
        turnSeq: question?.question_number,
        durationSeconds: pendingDuration.current || undefined,
      });
      pendingVideo.current = null;
      pendingAudio.current = null;
      setProcessing(false);
      if (next.done) { await finishInterview(); return; }
      setQuestion(next);
      playQuestionAudio(next);
    } catch (err: any) {
      setProcessing(false);
      if (err?.status === 410 || err?.status === 409) { setErrorMsg(err.message); setPhase('error'); }
      else setTurnError(err?.message || 'Network problem submitting your answer. Your recording is kept — please retry.');
    }
  };

  const retryTurn = async () => {
    await submitTurn(textAnswer.trim() || undefined);
  };

  const finishInterview = async () => {
    try {
      const res = await interviewApi.complete(token);
      setCompleteMessage(res?.message || 'Your interview is complete. Thank you for your time.');
    } catch {
      setCompleteMessage('Your interview has ended. Thank you for your time.');
    } finally {
      stopStream();
      setPhase('complete');
    }
  };

  const endInterviewEarly = async () => {
    if (!confirm('End the interview now? You will not be able to answer the remaining questions.')) return;
    await finishInterview();
  };

  // ================= render =================

  if (phase === 'loading') return <Centered><Loader2 className="h-8 w-8 animate-spin text-primary" /></Centered>;

  if (phase === 'error') {
    return (
      <Centered>
        <div className="w-full max-w-md rounded-2xl border border-border bg-card p-8 text-center shadow-xl">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10">
            <AlertCircle className="h-6 w-6 text-destructive" />
          </div>
          <h1 className="text-lg font-bold text-foreground">Interview unavailable</h1>
          <p className="mt-2 text-base font-semibold text-foreground">{errorMsg}</p>
          <p className="mt-4 text-sm font-semibold text-foreground">Please contact the recruiter who sent you this link.</p>
        </div>
      </Centered>
    );
  }

  if (phase === 'complete') {
    return (
      <Centered>
        <div className="w-full max-w-md rounded-2xl border border-border bg-card p-8 text-center shadow-xl">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-success/15">
            <CheckCircle2 className="h-7 w-7 text-success" />
          </div>
          <h1 className="text-xl font-bold text-foreground">Interview complete</h1>
          <p className="mt-2 text-base font-semibold text-foreground">{completeMessage}</p>
          <p className="mt-4 text-sm font-semibold text-foreground">The hiring team will review your responses. You can close this tab.</p>
        </div>
      </Centered>
    );
  }

  if (phase === 'device-check') {
    const resuming = session?.status === 'in_progress';
    return (
      <Centered>
        <div className="w-full max-w-2xl rounded-2xl border border-border bg-card p-6 shadow-xl sm:p-8">
          <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-primary">AI Video Interview</p>
          <h1 className="mt-2 text-2xl font-bold tracking-tight text-foreground">{session?.job_title}</h1>
          <p className="mt-2 text-base font-semibold text-foreground">
            {resuming
              ? `Welcome back, ${session?.candidate_first_name}. Let's continue your interview.`
              : `Hi ${session?.candidate_first_name}, let's get you set up. This is a video interview with an AI interviewer.`}
          </p>

          <div className="mt-6 grid gap-5 md:grid-cols-[1.1fr_1fr]">
            <div>
              <div className="relative aspect-video w-full overflow-hidden rounded-xl border border-border bg-black">
                {media === 'granted' ? (
                  <video ref={videoElRef} autoPlay muted playsInline className="h-full w-full object-cover [transform:scaleX(-1)]" />
                ) : (
                  <div className="flex h-full flex-col items-center justify-center gap-2 text-white/70">
                    <Video className="h-8 w-8" />
                    <span className="text-xs">Camera preview</span>
                  </div>
                )}
              </div>
              {media !== 'granted' && (
                <button
                  onClick={requestMedia}
                  disabled={media === 'requesting'}
                  className="mt-3 flex h-10 w-full items-center justify-center gap-2 rounded-xl border border-border bg-background text-sm font-semibold hover:bg-muted disabled:opacity-50"
                >
                  {media === 'requesting' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Video className="h-4 w-4" />}
                  Enable camera &amp; microphone
                </button>
              )}
            </div>

            <div className="space-y-2 text-sm">
              <Check label="Camera" ok={camOn} bad={media === 'denied' || media === 'unavailable'} />
              <Check label="Microphone" ok={micOn} bad={media === 'denied' || media === 'unavailable'} />
              <Check label="Speaker" ok={speakerOk} />
              <Check label="Internet connection" ok={online} bad={!online} />

              <div className="!mt-4 rounded-xl border border-border bg-muted/30 p-3 text-sm font-medium text-foreground">
                <p className="font-semibold text-foreground">Before you start</p>
                <ul className="mt-1.5 space-y-1">
                  <li>• Sit in a quiet, well-lit place.</li>
                  <li>• Keep your face visible and centred.</li>
                  <li>• Answer each question out loud, then press “Finish answer”.</li>
                  <li>• Complete the interview in one sitting.</li>
                </ul>
              </div>
            </div>
          </div>

          {media === 'denied' && (
            <p className="mt-3 text-xs font-medium text-destructive">
              Camera/microphone access was blocked. Enable it in your browser’s site settings and click “Enable camera &amp; microphone” again, or continue with typed answers below.
            </p>
          )}
          {(media === 'unavailable' || media === 'unsupported') && (
            <p className="mt-3 text-xs font-medium text-destructive">
              {media === 'unsupported'
                ? 'Your browser does not support in-browser recording. Please use a recent Chrome or Edge on a laptop/desktop, or continue with typed answers.'
                : 'No camera or microphone was detected. You can continue with typed answers.'}
            </p>
          )}
          {turnError && <p className="mt-3 text-xs font-medium text-destructive">{turnError}</p>}

          <div className="mt-6 flex flex-col gap-2 sm:flex-row">
            <button
              onClick={startInterview}
              disabled={processing || media === 'requesting'}
              className="flex h-12 flex-1 items-center justify-center gap-2 rounded-xl bg-primary text-sm font-bold text-primary-foreground shadow-lg shadow-primary/20 hover:opacity-90 disabled:opacity-50"
            >
              {processing || media === 'requesting'
                ? <><Loader2 className="h-4 w-4 animate-spin" /> Preparing…</>
                : <><Video className="h-4 w-4" /> {resuming ? 'Continue interview' : 'Start interview'}</>}
            </button>
            {media !== 'granted' && (
              <button
                onClick={() => { setUseTextFallback(true); startInterview(); }}
                className="flex h-12 items-center justify-center gap-2 rounded-xl border border-border bg-background px-4 text-sm font-semibold hover:bg-muted"
              >
                <Keyboard className="h-4 w-4" /> Continue with typed answers
              </button>
            )}
          </div>
        </div>
      </Centered>
    );
  }

  // ---- phase === 'interview' ----
  const qNum = question?.question_number || 1;
  const qTotal = question?.total_questions || session?.total_questions || 1;
  const mmss = `${String(Math.floor(recSeconds / 60)).padStart(2, '0')}:${String(recSeconds % 60).padStart(2, '0')}`;

  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col px-4 py-5 sm:py-8">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs font-bold uppercase tracking-[0.16em] text-muted-foreground">
          AI Video Interview · {session?.job_title}
        </p>
        <div className="flex items-center gap-3">
          <StatusPill on={camOn} onIcon={<Video size={13} />} offIcon={<VideoOff size={13} />} label={camOn ? 'Camera on' : 'Camera off'} />
          <StatusPill on={micOn} onIcon={<Mic size={13} />} offIcon={<MicOff size={13} />} label={micOn ? 'Mic on' : 'Mic off'} />
          <button
            onClick={endInterviewEarly}
            className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-1.5 text-xs font-semibold text-destructive hover:bg-destructive/20"
          >
            End interview
          </button>
        </div>
      </div>

      <div className="mb-4 h-1.5 w-full overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuenow={qNum} aria-valuemax={qTotal}>
        <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${Math.min(100, (qNum / qTotal) * 100)}%` }} />
      </div>

      <div className="grid flex-1 gap-4 lg:grid-cols-[1.4fr_1fr]">
        {/* Candidate video */}
        <div className="relative overflow-hidden rounded-2xl border border-border bg-black">
          {useTextFallback ? (
            <div className="flex h-full min-h-[240px] flex-col items-center justify-center gap-2 p-6 text-center text-white/60">
              <Keyboard className="h-8 w-8" />
              <span className="text-sm">Typed-answer mode — no camera</span>
            </div>
          ) : (
            <video ref={videoElRef} autoPlay muted playsInline className="h-full min-h-[240px] w-full object-cover [transform:scaleX(-1)]" />
          )}
          {recording && (
            <div className="absolute left-3 top-3 flex items-center gap-1.5 rounded-full bg-destructive px-2.5 py-1 text-xs font-bold text-white" aria-live="polite">
              <Circle size={9} className="animate-pulse fill-white" /> REC {mmss}
            </div>
          )}
        </div>

        {/* AI interviewer + controls */}
        <div className="flex flex-col gap-4">
          <div className="rounded-2xl border border-border bg-card p-5">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-primary">
              <div className={`flex h-8 w-8 items-center justify-center rounded-full bg-primary/10 ${aiSpeaking ? 'animate-pulse' : ''}`}>
                <Volume2 size={15} />
              </div>
              AI Interviewer
            </div>

            <p className="mt-3 text-lg font-medium leading-relaxed text-foreground">{question?.question_text}</p>

            <div className="mt-2 flex items-center gap-3 text-xs text-muted-foreground" aria-live="polite">
              {aiSpeaking ? (
                <span className="flex items-center gap-1.5 text-primary">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-primary" /> Speaking…
                </span>
              ) : recording ? (
                <span className="flex items-center gap-1.5 text-destructive">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-destructive" /> Listening — recording your answer
                </span>
              ) : processing ? (
                <span>Processing your answer…</span>
              ) : (
                <span>Waiting for your answer</span>
              )}
              {!aiSpeaking && question?.audio_file && (
                <button onClick={replayAudio} className="flex items-center gap-1 hover:text-foreground">
                  <Play size={12} /> Replay
                </button>
              )}
            </div>

            <p className="mt-3 text-xs font-semibold text-muted-foreground">
              {question?.is_followup ? 'Follow-up question' : `Question ${qNum} of ${qTotal}`}
            </p>
          </div>

          <div className="rounded-2xl border border-border bg-card p-5">
            {processing ? (
              <div className="flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" /> Processing…
              </div>
            ) : useTextFallback ? (
              <div>
                <label htmlFor="ans" className="sr-only">Your answer</label>
                <textarea
                  id="ans"
                  value={textAnswer}
                  onChange={(e) => setTextAnswer(e.target.value)}
                  placeholder="Type your answer…"
                  className="h-28 w-full resize-none rounded-xl border border-border bg-background p-3 text-sm outline-none focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30"
                />
                <button
                  onClick={turnError ? retryTurn : submitTextAnswer}
                  disabled={!textAnswer.trim() && !turnError}
                  className="mt-3 flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-primary text-sm font-bold text-primary-foreground hover:opacity-90 disabled:opacity-50"
                >
                  {turnError ? 'Retry submit' : 'Submit answer'}
                </button>
              </div>
            ) : recording ? (
              <button
                onClick={stopAndSubmit}
                aria-label="Finish answer and submit"
                className="flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-destructive/10 text-sm font-bold text-destructive hover:bg-destructive/20 focus-visible:ring-2 focus-visible:ring-destructive/40"
              >
                <Square size={14} /> Finish answer ({mmss})
              </button>
            ) : turnError ? (
              <div>
                <p className="mb-3 text-center text-xs font-medium text-destructive">{turnError}</p>
                <button
                  onClick={retryTurn}
                  className="flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-primary text-sm font-bold text-primary-foreground hover:opacity-90"
                >
                  <RefreshCw size={14} /> Retry submitting answer
                </button>
              </div>
            ) : (
              <button
                onClick={beginRecording}
                disabled={aiSpeaking}
                aria-label="Start recording your answer"
                className="flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-primary text-sm font-bold text-primary-foreground shadow-lg shadow-primary/20 hover:opacity-90 disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-primary/40"
              >
                <Mic size={16} /> {aiSpeaking ? 'Please wait…' : 'Record answer'}
              </button>
            )}
            <p className="mt-3 text-center text-[11px] text-muted-foreground">
              Your video answer is recorded and reviewed by the hiring team. Do not refresh unless necessary — your progress is saved.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return <div className="flex min-h-screen items-center justify-center p-4">{children}</div>;
}

function Check({ label, ok, bad }: { label: string; ok: boolean; bad?: boolean }) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-border bg-background px-3 py-2">
      <span className="text-muted-foreground">{label}</span>
      {ok ? (
        <span className="flex items-center gap-1 text-xs font-semibold text-success"><CheckCircle2 size={14} /> Ready</span>
      ) : bad ? (
        <span className="flex items-center gap-1 text-xs font-semibold text-destructive"><AlertCircle size={14} /> Not available</span>
      ) : (
        <span className="flex items-center gap-1 text-xs font-semibold text-muted-foreground"><Loader2 size={13} className="animate-spin" /> Checking</span>
      )}
    </div>
  );
}

function StatusPill({ on, onIcon, offIcon, label }: { on: boolean; onIcon: React.ReactNode; offIcon: React.ReactNode; label: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-[11px] font-semibold ${
        on ? 'bg-success/15 text-success' : 'bg-muted text-muted-foreground'
      }`}
      aria-live="polite"
    >
      {on ? onIcon : offIcon} {label}
    </span>
  );
}
