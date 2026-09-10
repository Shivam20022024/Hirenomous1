'use client';

import { useState, useEffect, useRef } from 'react';
import { Bot, Save, Sparkles, MessageSquare, Play, PlayCircle, Loader2, X } from 'lucide-react';
import { fetchApi } from '@/lib/api';

export default function AIRecruiterPage() {
  const [jobs, setJobs] = useState<any[]>([]);
  const [jobId, setJobId] = useState('');
  const [config, setConfig] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  
  // Chat Simulation
  const [messages, setMessages] = useState<{role: string, content: string}[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchApi('/jobs').then(setJobs).catch(console.error);
  }, []);

  useEffect(() => {
    if (jobId) {
      loadConfig();
    } else {
      setConfig(null);
      setMessages([]);
    }
  }, [jobId]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const loadConfig = async () => {
    setLoading(true);
    try {
      const data = await fetchApi(`/api/ai-recruiter/${jobId}`);
      setConfig(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (!config || !jobId) return;
    setSaving(true);
    try {
      const payload = {
        language: config.language || 'English',
        tone: config.tone || 'Professional',
        voice: config.voice || 'Rachel',
        screening_mode: config.screening_mode || 'Standard',
        is_active: config.is_active ?? true,
        status: config.status || 'Draft',
        screening_questions: config.screening_questions || []
      };
      const updated = await fetchApi(`/api/ai-recruiter/${jobId}`, {
        method: 'PUT',
        body: JSON.stringify(payload)
      });
      setConfig(updated);
      alert('Saved successfully!');
    } catch (err: any) {
      alert(`Failed to save: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleGenerateQuestions = async () => {
    if (!jobId) return;
    setLoading(true);
    try {
      const res = await fetchApi(`/api/ai-recruiter/${jobId}/generate-questions`, { method: 'POST' });
      if (res.questions) {
        setConfig({ ...config, screening_questions: res.questions });
      }
    } catch (err: any) {
      alert(`Failed to generate: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleQuestionChange = (index: number, field: string, value: string) => {
    const newQuestions = [...(config.screening_questions || [])];
    newQuestions[index] = { ...newQuestions[index], [field]: value };
    setConfig({ ...config, screening_questions: newQuestions });
  };

  const addQuestion = () => {
    const newQuestions = [...(config.screening_questions || [])];
    newQuestions.push({ question: '', expected_answer: '', key_keywords: [] });
    setConfig({ ...config, screening_questions: newQuestions });
  };

  const removeQuestion = (index: number) => {
    const newQuestions = [...(config.screening_questions || [])];
    newQuestions.splice(index, 1);
    setConfig({ ...config, screening_questions: newQuestions });
  };

  const sendChatMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!chatInput.trim() || !jobId) return;

    const newMsgs = [...messages, { role: 'user', content: chatInput }];
    setMessages(newMsgs);
    setChatInput('');
    setChatLoading(true);

    try {
      const res = await fetchApi(`/api/ai-recruiter/${jobId}/simulate`, {
        method: 'POST',
        body: JSON.stringify({ messages: newMsgs })
      });
      setMessages([...newMsgs, { role: 'assistant', content: res.response }]);
    } catch (err: any) {
      setMessages([...newMsgs, { role: 'assistant', content: `Error: ${err.message}` }]);
    } finally {
      setChatLoading(false);
    }
  };

  return (
    <div className="mx-auto max-w-[1240px] space-y-6 px-5 py-9 lg:px-8 lg:py-14">
      <div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
        <div>
          <h1 className="text-3xl font-bold tracking-[-0.06em]">AI Hiring Assistant</h1>
          <p className="mt-2 text-base font-semibold text-foreground">Configure the AI voice agent for automated initial screening.</p>
        </div>
        <div className="flex gap-2">
          <select value={jobId} onChange={e => setJobId(e.target.value)} className="h-11 rounded-xl border border-border bg-card px-4 text-sm font-medium outline-none">
            <option value="">Select a job to configure</option>
            {jobs.map(j => <option key={j.id} value={j.id}>{j.title}</option>)}
          </select>
          <button onClick={handleSave} disabled={!jobId || saving} className="flex h-11 items-center justify-center rounded-xl bg-primary px-4 text-sm font-semibold text-primary-foreground shadow-lg hover:opacity-90 disabled:opacity-50">
            {saving ? <Loader2 size={16} className="animate-spin mr-2"/> : <Save size={16} className="mr-2" />} Save Config
          </button>
        </div>
      </div>

      {!jobId ? (
        <div className="rounded-2xl border border-dashed border-border p-12 text-center text-muted-foreground">
          Select a job from the dropdown above to configure the AI Hiring Assistant.
        </div>
      ) : loading && !config ? (
        <div className="p-12 text-center"><div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent"></div></div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[1.5fr_1fr]">
          <div className="space-y-6">
            <section className="rounded-2xl border border-border bg-card p-6">
              <h2 className="text-lg font-bold mb-4">Voice & Personality</h2>
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="text-sm font-medium">Language</label>
                  <select value={config?.language || 'English'} onChange={e => setConfig({...config, language: e.target.value})} className="mt-1 w-full rounded-xl border border-border bg-background p-3 text-sm">
                    <option>English</option>
                    <option>Spanish</option>
                    <option>French</option>
                  </select>
                </div>
                <div>
                  <label className="text-sm font-medium">Tone</label>
                  <select value={config?.tone || 'Professional'} onChange={e => setConfig({...config, tone: e.target.value})} className="mt-1 w-full rounded-xl border border-border bg-background p-3 text-sm">
                    <option>Professional</option>
                    <option>Friendly</option>
                    <option>Enthusiastic</option>
                    <option>Strict</option>
                  </select>
                </div>
                <div>
                  <label className="text-sm font-medium">Voice Selection</label>
                  <select value={config?.voice || 'Rachel'} onChange={e => setConfig({...config, voice: e.target.value})} className="mt-1 w-full rounded-xl border border-border bg-background p-3 text-sm">
                    <option value="Rachel">Rachel (Female, Clear)</option>
                    <option value="Drew">Drew (Male, Deep)</option>
                    <option value="Mimi">Mimi (Female, Childish)</option>
                  </select>
                </div>
                <div>
                  <label className="text-sm font-medium">Status</label>
                  <select value={config?.status || 'Draft'} onChange={e => setConfig({...config, status: e.target.value})} className="mt-1 w-full rounded-xl border border-border bg-background p-3 text-sm">
                    <option>Draft</option>
                    <option>Active</option>
                  </select>
                </div>
              </div>
            </section>

            <section className="rounded-2xl border border-border bg-card p-6">
              <div className="flex justify-between items-center mb-4">
                <h2 className="text-lg font-bold">Screening Questions</h2>
                <button onClick={handleGenerateQuestions} disabled={loading} className="flex items-center text-sm font-semibold text-primary hover:opacity-80">
                  <Sparkles size={14} className="mr-1" /> Auto-Generate
                </button>
              </div>
              
              <div className="space-y-4">
                {config?.screening_questions?.map((q: any, i: number) => (
                  <div key={i} className="rounded-xl border border-border bg-muted/30 p-4 relative">
                    <button onClick={() => removeQuestion(i)} className="absolute top-3 right-3 text-muted-foreground hover:text-destructive"><X size={14}/></button>
                    <div className="space-y-3">
                      <div>
                        <label className="text-xs font-semibold uppercase text-muted-foreground">Question {i+1}</label>
                        <textarea value={q.question} onChange={e => handleQuestionChange(i, 'question', e.target.value)} className="mt-1 w-full rounded-lg border border-border bg-background p-2 text-sm h-16" />
                      </div>
                      <div>
                        <label className="text-xs font-semibold uppercase text-muted-foreground">Expected Answer / Guidance</label>
                        <input value={q.expected_answer || ''} onChange={e => handleQuestionChange(i, 'expected_answer', e.target.value)} className="mt-1 w-full rounded-lg border border-border bg-background p-2 text-sm" />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
              <button onClick={addQuestion} className="mt-4 w-full rounded-xl border border-dashed border-border py-3 text-sm font-semibold text-muted-foreground hover:bg-muted">
                + Add Question
              </button>
            </section>
          </div>

          <div className="space-y-6">
            <section className="rounded-2xl border border-border bg-card flex flex-col h-[600px] shadow-lg overflow-hidden">
              <div className="border-b border-border p-4 bg-muted/50 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Bot size={18} className="text-primary"/>
                  <h2 className="font-bold">Test Simulator</h2>
                </div>
                <div className="flex items-center gap-1.5 text-xs font-medium text-success bg-success/10 px-2 py-1 rounded-full border border-success/20">
                   <div className="h-1.5 w-1.5 rounded-full bg-success animate-pulse"></div>
                   Ready
                </div>
              </div>

              <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-[repeating-linear-gradient(to_bottom,transparent_0,transparent_23px,var(--color-muted)_24px)]">
                {messages.length === 0 ? (
                  <div className="h-full flex flex-col items-center justify-center text-center text-muted-foreground p-6">
                    <MessageSquare size={32} className="mb-4 opacity-20"/>
                    <p className="text-sm">Type a message below to start chatting with the AI Hiring Assistant configured with these settings.</p>
                  </div>
                ) : (
                  messages.map((m, i) => (
                    <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                      <div className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm ${m.role === 'user' ? 'bg-primary text-primary-foreground rounded-tr-sm' : 'bg-muted text-foreground border border-border rounded-tl-sm'}`}>
                        {m.content}
                      </div>
                    </div>
                  ))
                )}
                {chatLoading && (
                  <div className="flex justify-start">
                    <div className="rounded-2xl px-4 py-2.5 bg-muted text-foreground border border-border rounded-tl-sm flex gap-1 items-center">
                       <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground animate-bounce"></span>
                       <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground animate-bounce" style={{animationDelay: '0.1s'}}></span>
                       <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground animate-bounce" style={{animationDelay: '0.2s'}}></span>
                    </div>
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>

              <form onSubmit={sendChatMessage} className="border-t border-border p-3 bg-card">
                <div className="flex items-center gap-2 relative">
                  <input 
                    value={chatInput} 
                    onChange={e => setChatInput(e.target.value)} 
                    placeholder="Type your response..." 
                    className="flex-1 rounded-full border border-border bg-muted px-4 py-2.5 text-sm outline-none focus:border-primary pr-12"
                  />
                  <button type="submit" disabled={chatLoading || !chatInput.trim()} className="absolute right-1.5 h-8 w-8 flex items-center justify-center rounded-full bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-50">
                    <PlayCircle size={18}/>
                  </button>
                </div>
              </form>
            </section>
          </div>
        </div>
      )}
    </div>
  );
}
