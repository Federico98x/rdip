'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Search, ArrowRight, AlertCircle, RefreshCw, FileText, Link as LinkIcon, 
  Download, CheckCircle2, Activity, Flame, Clock, ExternalLink, Copy,
  Hash, Users, Sparkles, Brain, Zap
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const POLL_INTERVAL = 1000;
const MAX_POLLS = 300;

const PROGRESS_MESSAGES = [
  { threshold: 10, message: "Connecting to Reddit API..." },
  { threshold: 25, message: "Extracting post content..." },
  { threshold: 35, message: "Loading comments..." },
  { threshold: 50, message: "Processing with AI..." },
  { threshold: 70, message: "Analyzing sentiment..." },
  { threshold: 85, message: "Enriching links..." },
  { threshold: 95, message: "Finalizing results..." },
];

interface SentimentObj {
  label: string;
  score: number;
  details: string;
}

interface EnrichedLink {
  url: string;
  title?: string;
  description?: string;
  type: string;
  domain: string;
  favicon?: string;
  context: string;
  relevance_score: number;
}

interface AnalysisResult {
  meta: {
    title: string;
    author: string;
    upvotes: number;
    total_comments: number;
    subreddit: string;
    created_utc: number;
    upvote_ratio: number;
    url: string;
    is_self: boolean;
    link_flair_text: string | null;
  };
  raw_post_text: string;
  raw_comments_text: string;
  summary_post: string;
  summary_comments: string;
  sentiment_post: SentimentObj;
  sentiment_comments: SentimentObj;
  consensus: string;
  key_controversies: string[];
  useful_links: EnrichedLink[];
}

interface JobStatus {
  job_id: string;
  status: 'queued' | 'processing' | 'completed' | 'failed';
  progress: number;
  result?: AnalysisResult;
  error?: string;
  created_at: string;
}

interface TrendingTopic {
  topic: string;
  mentions: number;
  sentiment: string;
  top_posts: Array<{ title: string; score: number; url: string }>;
  keywords: string[];
}

interface TrendingResponse {
  subreddit: string;
  period: string;
  analyzed_posts: number;
  topics: TrendingTopic[];
  overall_sentiment: string;
  generated_at: string;
}

type ViewMode = 'analyze' | 'trending';

export default function Home() {
  const [viewMode, setViewMode] = useState<ViewMode>('analyze');
  
  const [url, setUrl] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  
  const [subreddit, setSubreddit] = useState('');
  const [trendingPeriod, setTrendingPeriod] = useState<'day' | 'week' | 'month'>('week');
  const [trendingLimit, setTrendingLimit] = useState(10);
  const [isLoadingTrending, setIsLoadingTrending] = useState(false);
  const [trendingResult, setTrendingResult] = useState<TrendingResponse | null>(null);
  
  const [forceRefresh, setForceRefresh] = useState(false);
  const [deepScan, setDeepScan] = useState(false);
  const [liteMode, setLiteMode] = useState(false);
  const [backendHealth, setBackendHealth] = useState<'checking' | 'ok' | 'degraded' | 'down'>('checking');
  const [copied, setCopied] = useState(false);

  const getProgressMessage = (p: number) => {
    for (let i = PROGRESS_MESSAGES.length - 1; i >= 0; i--) {
      if (p >= PROGRESS_MESSAGES[i].threshold) {
        return PROGRESS_MESSAGES[i].message;
      }
    }
    return "Initializing...";
  };

  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch(`${API_URL}/v1/health`);
        if (res.ok) {
          setBackendHealth('ok');
        } else {
          setBackendHealth('degraded');
        }
      } catch {
        setBackendHealth('down');
      }
    };
    checkHealth();
  }, []);

  useEffect(() => {
    let pollTimer: NodeJS.Timeout;
    let polls = 0;

    const poll = async () => {
      if (!jobId || isAnalyzing === false) return;

      try {
        const res = await fetch(`${API_URL}/v1/status/${jobId}`);
        if (!res.ok) throw new Error('Failed to get status');
        
        const data: JobStatus = await res.json();
        setProgress(data.progress);

        if (data.status === 'completed' && data.result) {
          setResult(data.result);
          setIsAnalyzing(false);
          setJobId(null);
        } else if (data.status === 'failed') {
          setError(data.error || 'Analysis failed');
          setIsAnalyzing(false);
          setJobId(null);
        } else {
          polls++;
          if (polls > MAX_POLLS) {
            setError('Analysis timed out');
            setIsAnalyzing(false);
            setJobId(null);
          } else {
            pollTimer = setTimeout(poll, POLL_INTERVAL);
          }
        }
      } catch {
        polls++;
        if (polls > MAX_POLLS) {
          setError('Lost connection to backend');
          setIsAnalyzing(false);
        } else {
          pollTimer = setTimeout(poll, POLL_INTERVAL);
        }
      }
    };

    if (jobId) {
      poll();
    }

    return () => clearTimeout(pollTimer);
  }, [jobId, isAnalyzing]);

  const handleAnalyze = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url) return;
    
    setIsAnalyzing(true);
    setError(null);
    setResult(null);
    setProgress(0);

    try {
      const res = await fetch(`${API_URL}/v1/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          url,
          force_refresh: forceRefresh,
          deep_scan: deepScan,
          lite_mode: liteMode
        })
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to start analysis');
      }

      const data: JobStatus = await res.json();
      
      if (data.status === 'completed' && data.result) {
        setResult(data.result);
        setIsAnalyzing(false);
      } else {
        setJobId(data.job_id);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'An error occurred');
      setIsAnalyzing(false);
    }
  };

  const handleTrendingAnalysis = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!subreddit) return;
    
    setIsLoadingTrending(true);
    setError(null);
    setTrendingResult(null);

    try {
      const res = await fetch(
        `${API_URL}/v1/trending/${subreddit}?period=${trendingPeriod}&limit=${trendingLimit}`
      );

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to get trending topics');
      }

      const data: TrendingResponse = await res.json();
      setTrendingResult(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'An error occurred');
    } finally {
      setIsLoadingTrending(false);
    }
  };

  const handleDownload = (content: string, filename: string) => {
    const blob = new Blob([content], { type: 'text/plain' });
    const downloadUrl = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = downloadUrl;
    a.download = filename;
    a.click();
    window.URL.revokeObjectURL(downloadUrl);
  };

  const handleCopy = async (text: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const getSentimentColor = (label: string) => {
    switch (label.toLowerCase()) {
      case 'positivo': return 'text-emerald-400';
      case 'positive': return 'text-emerald-400';
      case 'negativo': return 'text-rose-400';
      case 'negative': return 'text-rose-400';
      case 'mixto': return 'text-amber-400';
      case 'mixed': return 'text-amber-400';
      case 'controversial': return 'text-violet-400';
      default: return 'text-slate-300';
    }
  };

  const getSentimentBg = (label: string) => {
    switch (label.toLowerCase()) {
      case 'positivo': case 'positive': return 'bg-emerald-500/15 border-emerald-500/30';
      case 'negativo': case 'negative': return 'bg-rose-500/15 border-rose-500/30';
      case 'mixto': case 'mixed': return 'bg-amber-500/15 border-amber-500/30';
      case 'controversial': return 'bg-violet-500/15 border-violet-500/30';
      default: return 'bg-slate-500/15 border-slate-500/30';
    }
  };

  const handleViewChange = (mode: ViewMode) => {
    setViewMode(mode);
    setError(null);
  };

  return (
    <div className="min-h-screen min-h-[100dvh] bg-[#0a0a0f] text-slate-100 flex flex-col selection:bg-cyan-500/30">
      <div className="fixed inset-0 z-0 overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-b from-[#0f0f1a] via-[#0a0a0f] to-[#050508]" />
        <div className="absolute top-0 left-1/4 w-[600px] h-[600px] bg-cyan-500/5 rounded-full blur-[120px]" />
        <div className="absolute bottom-0 right-1/4 w-[500px] h-[500px] bg-violet-500/5 rounded-full blur-[120px]" />
        <div className="absolute inset-0 bg-[url('/grid.svg')] bg-center opacity-[0.02]" />
      </div>
      
      <header className="fixed top-0 w-full z-50 border-b border-white/[0.06] bg-[#0a0a0f]/80 backdrop-blur-xl pt-[env(safe-area-inset-top)]">
        <div className="container mx-auto px-4 h-14 sm:h-16 flex items-center justify-between">
          <div 
            className="flex items-center gap-2 sm:gap-3 cursor-pointer group" 
            onClick={() => { handleViewChange('analyze'); setResult(null); setTrendingResult(null); }}
          >
            <div className="relative">
              <div className="absolute inset-0 bg-cyan-400/30 blur-xl opacity-0 group-hover:opacity-100 transition-opacity duration-500" />
              <div className="relative bg-gradient-to-br from-cyan-500 to-blue-600 p-2 sm:p-2.5 rounded-xl shadow-lg shadow-cyan-500/20">
                <Brain className="h-4 w-4 sm:h-5 sm:w-5 text-white" />
              </div>
            </div>
            <span className="text-lg sm:text-xl font-bold tracking-tight text-white">RDIP</span>
          </div>
          
          <nav className="flex items-center gap-1 p-1 bg-white/[0.03] border border-white/[0.06] rounded-xl">
            <button
              onClick={() => handleViewChange('analyze')}
              className={`flex items-center gap-1.5 sm:gap-2 px-3 sm:px-4 py-1.5 sm:py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                viewMode === 'analyze' 
                  ? 'bg-cyan-500/20 text-cyan-300 shadow-[inset_0_1px_0_rgba(255,255,255,0.1)]' 
                  : 'text-slate-400 hover:text-white hover:bg-white/[0.04]'
              }`}
            >
              <Search className="h-4 w-4" />
              <span className="hidden xs:inline">Analyze</span>
            </button>
            <button
              onClick={() => handleViewChange('trending')}
              className={`flex items-center gap-1.5 sm:gap-2 px-3 sm:px-4 py-1.5 sm:py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                viewMode === 'trending' 
                  ? 'bg-orange-500/20 text-orange-300 shadow-[inset_0_1px_0_rgba(255,255,255,0.1)]' 
                  : 'text-slate-400 hover:text-white hover:bg-white/[0.04]'
              }`}
            >
              <Flame className="h-4 w-4" />
              <span className="hidden xs:inline">Trending</span>
            </button>
          </nav>
          
          <div className="flex items-center">
            <div className={`flex items-center gap-1.5 sm:gap-2 px-2 sm:px-3 py-1 sm:py-1.5 rounded-lg border ${
              backendHealth === 'ok' 
                ? 'bg-emerald-500/10 border-emerald-500/20' 
                : 'bg-amber-500/10 border-amber-500/20'
            }`}>
              <div className="relative flex h-2 w-2">
                <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
                  backendHealth === 'ok' ? 'bg-emerald-400' : 'bg-amber-400'
                }`} />
                <span className={`relative inline-flex rounded-full h-2 w-2 ${
                  backendHealth === 'ok' ? 'bg-emerald-500' : 'bg-amber-500'
                }`} />
              </div>
              <span className={`text-xs font-medium tracking-wide hidden sm:block ${
                backendHealth === 'ok' ? 'text-emerald-400' : 'text-amber-400'
              }`}>
                {backendHealth === 'ok' ? 'ONLINE' : 'CONNECTING'}
              </span>
            </div>
          </div>
        </div>
      </header>

      <main className="flex-1 container mx-auto px-4 py-8 flex flex-col gap-6 sm:gap-8 max-w-6xl relative z-10 pt-20 sm:pt-28 pb-[calc(env(safe-area-inset-bottom)+2rem)]">
        <AnimatePresence mode="wait">
          {viewMode === 'analyze' && !result && !isAnalyzing && (
            <motion.div 
              key="analyze-hero"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={{ duration: 0.3, ease: "easeOut" }}
              className="flex flex-col gap-10"
            >
              <section className="flex flex-col items-center text-center gap-4 sm:gap-6 max-w-3xl mx-auto px-2">
                  <div className="inline-flex items-center gap-2 px-3 sm:px-4 py-1.5 sm:py-2 rounded-full bg-cyan-500/10 border border-cyan-500/20">
                    <Sparkles className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-cyan-400" />
                    <span className="text-cyan-300 text-xs sm:text-sm font-medium">AI-Powered Analysis</span>
                  </div>
                  
                  <h1 className="text-3xl sm:text-4xl md:text-6xl font-bold tracking-tight leading-[1.1]">
                    <span className="text-white">Unlock Reddit&apos;s</span>
                    <br />
                    <span className="bg-gradient-to-r from-cyan-400 via-blue-400 to-violet-400 bg-clip-text text-transparent">
                      Hidden Insights
                    </span>
                  </h1>
                  
                  <p className="text-base sm:text-lg text-slate-400 max-w-xl leading-relaxed">
                    Transform chaotic discussions into structured, actionable intelligence.
                  </p>
                </section>

                <div className="w-full max-w-2xl mx-auto space-y-4 sm:space-y-6">
                  <form onSubmit={handleAnalyze} className="relative">
                    <div className="absolute -inset-[1px] bg-gradient-to-r from-cyan-500/50 via-blue-500/50 to-violet-500/50 rounded-2xl blur-sm opacity-0 group-hover:opacity-100 transition-opacity" />
                    <div className="relative flex flex-col sm:flex-row gap-2 sm:gap-3 p-2 sm:p-3 bg-[#111118] border border-white/[0.08] rounded-2xl shadow-2xl shadow-black/50">
                      <div className="flex items-center gap-2 flex-1">
                        <div className="pl-2 sm:pl-3 flex items-center pointer-events-none">
                          <Search className="h-5 w-5 text-slate-500" />
                        </div>
                        <Input 
                          value={url}
                          onChange={(e) => setUrl(e.target.value)}
                          placeholder="Paste Reddit URL here..." 
                          className="border-none shadow-none focus-visible:ring-0 bg-transparent h-10 sm:h-12 text-sm sm:text-base text-white placeholder:text-slate-600"
                          disabled={isAnalyzing}
                        />
                      </div>
                      <Button 
                        type="submit" 
                        className="h-10 sm:h-12 px-4 sm:px-6 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-semibold shadow-lg shadow-cyan-500/25 transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed w-full sm:w-auto" 
                        disabled={isAnalyzing || !url}
                      >
                        <span>Analyze</span>
                        <ArrowRight className="h-4 w-4 ml-2" />
                      </Button>
                    </div>
                  </form>

                  <div className="flex flex-wrap justify-center gap-3 sm:gap-6 text-sm">
                    <label className="flex items-center gap-2 sm:gap-3 cursor-pointer group">
                      <Switch 
                        id="force-refresh" 
                        checked={forceRefresh} 
                        onCheckedChange={setForceRefresh} 
                        className="data-[state=checked]:bg-cyan-500 scale-90 sm:scale-100" 
                      />
                      <span className="text-slate-400 group-hover:text-slate-200 transition-colors text-xs sm:text-sm">Fresh</span>
                    </label>
                    <label className="flex items-center gap-2 sm:gap-3 cursor-pointer group">
                      <Switch 
                        id="deep-scan" 
                        checked={deepScan} 
                        onCheckedChange={setDeepScan} 
                        className="data-[state=checked]:bg-cyan-500 scale-90 sm:scale-100" 
                      />
                      <span className="text-slate-400 group-hover:text-slate-200 transition-colors text-xs sm:text-sm">Deep Scan</span>
                    </label>
                    <label className="flex items-center gap-2 sm:gap-3 cursor-pointer group" title="Lite mode limits content to avoid API quota issues">
                      <Switch 
                        id="lite-mode" 
                        checked={liteMode} 
                        onCheckedChange={setLiteMode} 
                        className="data-[state=checked]:bg-emerald-500 scale-90 sm:scale-100" 
                      />
                      <span className="text-slate-400 group-hover:text-slate-200 transition-colors flex items-center gap-1 text-xs sm:text-sm">
                        <Zap className="h-3 w-3 sm:h-3.5 sm:w-3.5" />
                        Lite
                      </span>
                    </label>
                  </div>
                </div>
            </motion.div>
          )}

          {viewMode === 'trending' && !trendingResult && !isLoadingTrending && (
            <motion.div
              key="trending-hero"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={{ duration: 0.3, ease: "easeOut" }}
              className="w-full max-w-xl mx-auto space-y-8"
            >
              <div className="text-center space-y-4">
                <div className="mx-auto w-16 h-16 rounded-2xl bg-gradient-to-br from-orange-500 to-rose-500 flex items-center justify-center shadow-lg shadow-orange-500/25">
                  <Flame className="h-8 w-8 text-white" />
                </div>
                <h2 className="text-3xl font-bold text-white">Discover Trends</h2>
                <p className="text-slate-400">Analyze the pulse of any community</p>
              </div>
              
              <form onSubmit={handleTrendingAnalysis} className="space-y-5 bg-[#111118] p-6 rounded-2xl border border-white/[0.06]">
                <div className="space-y-4">
                  <div className="relative">
                    <div className="flex items-center gap-2 p-3 bg-[#0a0a0f] border border-white/[0.08] rounded-xl focus-within:border-orange-500/50 transition-colors">
                      <span className="text-slate-500 font-mono text-sm pl-1">r/</span>
                      <Input 
                        value={subreddit}
                        onChange={(e) => setSubreddit(e.target.value.replace(/^r\//, ''))}
                        placeholder="technology" 
                        className="border-none shadow-none focus-visible:ring-0 bg-transparent h-10 text-base text-white placeholder:text-slate-600"
                        disabled={isLoadingTrending}
                      />
                    </div>
                  </div>
                  
                  <div className="grid grid-cols-2 gap-3">
                    <Select value={trendingPeriod} onValueChange={(v) => setTrendingPeriod(v as 'day' | 'week' | 'month')}>
                      <SelectTrigger className="h-12 bg-[#0a0a0f] border-white/[0.08] rounded-xl text-white">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="bg-[#1a1a24] border-white/[0.1]">
                        <SelectItem value="day" className="text-slate-200 focus:bg-white/10 focus:text-white">Past 24 Hours</SelectItem>
                        <SelectItem value="week" className="text-slate-200 focus:bg-white/10 focus:text-white">Past Week</SelectItem>
                        <SelectItem value="month" className="text-slate-200 focus:bg-white/10 focus:text-white">Past Month</SelectItem>
                      </SelectContent>
                    </Select>
                    
                    <Select value={String(trendingLimit)} onValueChange={(v) => setTrendingLimit(Number(v))}>
                      <SelectTrigger className="h-12 bg-[#0a0a0f] border-white/[0.08] rounded-xl text-white">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent className="bg-[#1a1a24] border-white/[0.1]">
                        <SelectItem value="5" className="text-slate-200 focus:bg-white/10 focus:text-white">Top 5</SelectItem>
                        <SelectItem value="10" className="text-slate-200 focus:bg-white/10 focus:text-white">Top 10</SelectItem>
                        <SelectItem value="15" className="text-slate-200 focus:bg-white/10 focus:text-white">Top 15</SelectItem>
                        <SelectItem value="25" className="text-slate-200 focus:bg-white/10 focus:text-white">Top 25</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                
                <Button 
                  type="submit" 
                  className="w-full h-12 rounded-xl bg-gradient-to-r from-orange-500 to-rose-500 hover:from-orange-400 hover:to-rose-400 text-white font-semibold shadow-lg shadow-orange-500/25 transition-all disabled:opacity-40"
                  disabled={isLoadingTrending || !subreddit}
                >
                  {isLoadingTrending ? (
                    <RefreshCw className="h-5 w-5 animate-spin" />
                  ) : (
                    'Analyze Trends'
                  )}
                </Button>
              </form>
            </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {error && (
            <motion.div
              key="error"
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className="max-w-2xl mx-auto w-full"
            >
              <Alert className="bg-rose-500/10 border-rose-500/30">
                <AlertCircle className="h-5 w-5 text-rose-400" />
                <AlertTitle className="text-rose-300 font-semibold ml-2">Error</AlertTitle>
                <AlertDescription className="text-rose-200/80 ml-2 mt-1">{error}</AlertDescription>
              </Alert>
            </motion.div>
          )}
        </AnimatePresence>

        {(isAnalyzing || isLoadingTrending) && (
          <motion.div 
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="max-w-md mx-auto w-full text-center space-y-6 py-12"
          >
            <div className="relative mx-auto w-20 h-20">
              <div className="absolute inset-0 rounded-full border-2 border-cyan-500/20" />
              <div className="absolute inset-0 rounded-full border-t-2 border-cyan-400 animate-spin" />
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-lg font-bold text-white">{progress}%</span>
              </div>
            </div>
            
            <div className="space-y-2">
              <p className="text-lg font-medium text-white">{getProgressMessage(progress)}</p>
              <p className="text-sm text-slate-500">Processing data...</p>
            </div>
            
            <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
              <motion.div 
                className="h-full bg-gradient-to-r from-cyan-500 to-violet-500"
                initial={{ width: 0 }}
                animate={{ width: `${progress}%` }}
                transition={{ duration: 0.3 }}
              />
            </div>
          </motion.div>
        )}

        {trendingResult && viewMode === 'trending' && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-6"
          >
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 bg-[#111118] p-5 rounded-2xl border border-white/[0.06]">
              <div>
                <h2 className="text-2xl font-bold flex items-center gap-3 text-white">
                  <span className="p-2 rounded-lg bg-orange-500/20">
                    <Flame className="h-5 w-5 text-orange-400" />
                  </span>
                  r/{trendingResult.subreddit}
                </h2>
                <div className="flex items-center gap-3 mt-2">
                  <Badge variant="outline" className="border-white/10 bg-white/5 text-slate-300">
                    {trendingResult.analyzed_posts} posts
                  </Badge>
                  <span className="text-sm text-slate-500 capitalize">{trendingResult.period}</span>
                </div>
              </div>
              <Button 
                onClick={() => setTrendingResult(null)} 
                variant="outline" 
                className="border-white/10 bg-white/5 text-slate-300 hover:bg-white/10 hover:text-white"
              >
                New Analysis
              </Button>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {trendingResult.topics.map((topic, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.05 }}
                >
                  <Card className="h-full bg-[#111118] border-white/[0.06] hover:border-white/[0.12] transition-colors">
                    <CardHeader className="pb-3">
                      <div className="flex justify-between items-start mb-2">
                        <Badge className={`${getSentimentBg(topic.sentiment)} text-xs font-medium`}>
                          <span className={getSentimentColor(topic.sentiment)}>{topic.sentiment}</span>
                        </Badge>
                        <div className="flex items-center gap-1 text-xs text-slate-500">
                          <Hash className="h-3 w-3" />
                          {topic.mentions}
                        </div>
                      </div>
                      <CardTitle className="text-lg text-white leading-snug">
                        {topic.topic}
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <div className="flex flex-wrap gap-1.5">
                        {topic.keywords.slice(0, 4).map((kw, j) => (
                          <span key={j} className="px-2 py-0.5 rounded bg-white/5 text-xs text-slate-400">
                            {kw}
                          </span>
                        ))}
                      </div>
                      <div className="space-y-2 pt-2 border-t border-white/[0.06]">
                        {topic.top_posts.slice(0, 2).map((post, j) => (
                          <a 
                            key={j} 
                            href={post.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="block text-sm text-slate-400 hover:text-cyan-400 transition-colors line-clamp-2"
                          >
                            {post.title}
                          </a>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                </motion.div>
              ))}
            </div>
          </motion.div>
        )}

        {result && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-6"
          >
            <div className="bg-[#111118] border border-white/[0.06] rounded-2xl p-6">
              <div className="flex flex-col lg:flex-row gap-6 justify-between items-start">
                <div className="space-y-3 flex-1">
                  <div className="flex items-center gap-3">
                    <Badge className="bg-orange-500/15 text-orange-400 border-orange-500/30">
                      r/{result.meta.subreddit}
                    </Badge>
                    <span className="text-slate-500 text-sm flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      <span suppressHydrationWarning>{new Date(result.meta.created_utc * 1000).toLocaleDateString()}</span>
                    </span>
                  </div>
                  <h2 className="text-xl md:text-2xl font-bold text-white leading-tight">
                    <a href={result.meta.url} target="_blank" rel="noopener noreferrer" className="hover:text-cyan-400 transition-colors">
                      {result.meta.title}
                    </a>
                  </h2>
                  <div className="flex items-center gap-2 text-sm text-slate-400">
                    <Users className="h-4 w-4" />
                    <span>u/{result.meta.author}</span>
                  </div>
                </div>

                <div className="flex gap-2">
                  <Button 
                    variant="outline" 
                    size="sm" 
                    onClick={() => handleCopy(JSON.stringify(result, null, 2))}
                    className="bg-white/5 border-white/10 text-slate-300 hover:bg-white/10 hover:text-white"
                  >
                    {copied ? <CheckCircle2 className="h-4 w-4 text-emerald-400" /> : <Copy className="h-4 w-4" />}
                    <span className="ml-2">JSON</span>
                  </Button>
                  <Button 
                    variant="outline" 
                    size="sm" 
                    onClick={() => setResult(null)}
                    className="bg-cyan-500/10 border-cyan-500/30 text-cyan-400 hover:bg-cyan-500/20 hover:text-cyan-300"
                  >
                    <RefreshCw className="h-4 w-4" />
                    <span className="ml-2">New</span>
                  </Button>
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-6">
                <div className="bg-[#0a0a0f] rounded-xl p-4 border border-white/[0.04]">
                  <div className="text-slate-500 text-xs font-medium uppercase tracking-wider mb-1">Upvotes</div>
                  <div className="text-xl font-bold text-white flex items-baseline gap-2">
                    {result.meta.upvotes.toLocaleString()}
                    <span className="text-xs font-normal text-emerald-400">{(result.meta.upvote_ratio * 100).toFixed(0)}%</span>
                  </div>
                </div>
                <div className="bg-[#0a0a0f] rounded-xl p-4 border border-white/[0.04]">
                  <div className="text-slate-500 text-xs font-medium uppercase tracking-wider mb-1">Comments</div>
                  <div className="text-xl font-bold text-white">{result.meta.total_comments.toLocaleString()}</div>
                </div>
                <div className={`rounded-xl p-4 border ${getSentimentBg(result.sentiment_post.label)}`}>
                  <div className="text-slate-400 text-xs font-medium uppercase tracking-wider mb-1">Post</div>
                  <div className={`text-lg font-bold ${getSentimentColor(result.sentiment_post.label)}`}>{result.sentiment_post.label}</div>
                </div>
                <div className={`rounded-xl p-4 border ${getSentimentBg(result.sentiment_comments.label)}`}>
                  <div className="text-slate-400 text-xs font-medium uppercase tracking-wider mb-1">Comments</div>
                  <div className={`text-lg font-bold ${getSentimentColor(result.sentiment_comments.label)}`}>{result.sentiment_comments.label}</div>
                </div>
              </div>
            </div>

            <Tabs defaultValue="summary" className="w-full">
              <div className="flex justify-center mb-6">
                <TabsList className="bg-[#111118] p-1 border border-white/[0.06] rounded-xl h-auto">
                  {['summary', 'sentiment', 'links', 'raw'].map((tab) => (
                    <TabsTrigger 
                      key={tab} 
                      value={tab}
                      className="rounded-lg px-5 py-2.5 text-slate-400 data-[state=active]:bg-cyan-500/20 data-[state=active]:text-cyan-300 hover:text-white transition-colors capitalize"
                    >
                      {tab}
                    </TabsTrigger>
                  ))}
                </TabsList>
              </div>

              <TabsContent value="summary" className="space-y-4 mt-0">
                <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                  <Card className="lg:col-span-2 bg-[#111118] border-white/[0.06]">
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2 text-cyan-400">
                        <FileText className="h-5 w-5" />
                        Summary
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-5">
                      <div>
                        <Label className="text-slate-500 text-xs uppercase tracking-wider">Post</Label>
                        <p className="text-slate-200 leading-relaxed mt-2">{result.summary_post || "No summary available."}</p>
                      </div>
                      <div className="h-px bg-white/[0.06]" />
                      <div>
                        <Label className="text-slate-500 text-xs uppercase tracking-wider">Discussion</Label>
                        <p className="text-slate-200 leading-relaxed mt-2">{result.summary_comments || "No summary available."}</p>
                      </div>
                    </CardContent>
                  </Card>

                  <div className="space-y-4">
                    <Card className="bg-[#111118] border-white/[0.06]">
                      <CardHeader className="pb-3">
                        <CardTitle className="text-sm text-white">Consensus</CardTitle>
                      </CardHeader>
                      <CardContent>
                        <p className="text-slate-300 text-sm leading-relaxed">{result.consensus}</p>
                      </CardContent>
                    </Card>

                    <Card className="bg-[#111118] border-white/[0.06]">
                      <CardHeader className="pb-3">
                        <CardTitle className="text-sm text-rose-400">Controversies</CardTitle>
                      </CardHeader>
                      <CardContent>
                        {result.key_controversies.length > 0 ? (
                          <ul className="space-y-2">
                            {result.key_controversies.map((c, i) => (
                              <li key={i} className="flex gap-2 text-sm text-slate-300">
                                <span className="text-rose-400 mt-0.5">•</span>
                                {c}
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <p className="text-slate-500 text-sm">No controversies detected.</p>
                        )}
                      </CardContent>
                    </Card>
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="sentiment" className="mt-0">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <Card className="bg-[#111118] border-white/[0.06] overflow-hidden">
                    <div className={`h-1 w-full ${result.sentiment_post.score > 0.5 ? 'bg-gradient-to-r from-emerald-500 to-emerald-400' : 'bg-gradient-to-r from-rose-500 to-rose-400'}`} />
                    <CardHeader>
                      <CardTitle className="text-white">Post Sentiment</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="flex items-end gap-3">
                        <span className="text-4xl font-bold text-white">{(result.sentiment_post.score * 100).toFixed(0)}</span>
                        <span className={`text-lg font-medium mb-1 ${getSentimentColor(result.sentiment_post.label)}`}>{result.sentiment_post.label}</span>
                      </div>
                      <p className="text-slate-400 text-sm">{result.sentiment_post.details}</p>
                    </CardContent>
                  </Card>

                  <Card className="bg-[#111118] border-white/[0.06] overflow-hidden">
                    <div className={`h-1 w-full ${result.sentiment_comments.score > 0.5 ? 'bg-gradient-to-r from-emerald-500 to-emerald-400' : 'bg-gradient-to-r from-rose-500 to-rose-400'}`} />
                    <CardHeader>
                      <CardTitle className="text-white">Community Sentiment</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="flex items-end gap-3">
                        <span className="text-4xl font-bold text-white">{(result.sentiment_comments.score * 100).toFixed(0)}</span>
                        <span className={`text-lg font-medium mb-1 ${getSentimentColor(result.sentiment_comments.label)}`}>{result.sentiment_comments.label}</span>
                      </div>
                      <p className="text-slate-400 text-sm">{result.sentiment_comments.details}</p>
                    </CardContent>
                  </Card>
                </div>
              </TabsContent>

              <TabsContent value="links" className="mt-0">
                <div className="space-y-3">
                  {result.useful_links.length === 0 ? (
                    <div className="text-center py-16 text-slate-500 bg-[#111118] rounded-2xl border border-white/[0.06]">
                      <LinkIcon className="h-10 w-10 mx-auto mb-3 opacity-30" />
                      <p>No links found</p>
                    </div>
                  ) : (
                    result.useful_links.map((link, i) => (
                      <Card key={i} className="bg-[#111118] border-white/[0.06] hover:border-white/[0.12] transition-colors">
                        <CardContent className="p-4 flex items-start gap-4">
                          <div className="h-10 w-10 rounded-lg bg-white/5 flex items-center justify-center shrink-0">
                            {link.favicon ? (
                              <img src={link.favicon} alt="" className="h-5 w-5" />
                            ) : (
                              <LinkIcon className="h-4 w-4 text-slate-500" />
                            )}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center justify-between gap-3">
                              <a href={link.url} target="_blank" rel="noopener noreferrer" className="font-medium text-cyan-400 hover:text-cyan-300 truncate flex items-center gap-2">
                                {link.title || link.domain}
                                <ExternalLink className="h-3 w-3 opacity-50" />
                              </a>
                              <Badge variant="outline" className="bg-white/5 border-white/10 text-slate-400 text-xs shrink-0">
                                {link.type}
                              </Badge>
                            </div>
                            <p className="text-sm text-slate-500 mt-1 line-clamp-1">{link.description || link.context}</p>
                            <div className="flex items-center gap-4 mt-2 text-xs text-slate-600">
                              <span className="flex items-center gap-1">
                                <Activity className="h-3 w-3" />
                                {(link.relevance_score * 100).toFixed(0)}% relevant
                              </span>
                              <span>{link.domain}</span>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    ))
                  )}
                </div>
              </TabsContent>

              <TabsContent value="raw" className="mt-0">
                <Card className="bg-[#111118] border-white/[0.06]">
                  <CardContent className="p-0">
                    <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-white/[0.06]">
                      <div className="p-4">
                        <div className="flex justify-between items-center mb-3">
                          <span className="font-medium text-white text-sm">Post Source</span>
                          <Button 
                            size="sm" 
                            variant="ghost" 
                            onClick={() => handleDownload(result.raw_post_text, 'post.txt')}
                            className="text-slate-400 hover:text-white hover:bg-white/10"
                          >
                            <Download className="h-4 w-4" />
                          </Button>
                        </div>
                        <ScrollArea className="h-[350px] w-full rounded-lg bg-[#0a0a0f] p-4 font-mono text-xs text-slate-400">
                          {result.raw_post_text}
                        </ScrollArea>
                      </div>
                      <div className="p-4">
                        <div className="flex justify-between items-center mb-3">
                          <span className="font-medium text-white text-sm">Comments Source</span>
                          <Button 
                            size="sm" 
                            variant="ghost" 
                            onClick={() => handleDownload(result.raw_comments_text, 'comments.txt')}
                            className="text-slate-400 hover:text-white hover:bg-white/10"
                          >
                            <Download className="h-4 w-4" />
                          </Button>
                        </div>
                        <ScrollArea className="h-[350px] w-full rounded-lg bg-[#0a0a0f] p-4 font-mono text-xs text-slate-400">
                          {result.raw_comments_text}
                        </ScrollArea>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </TabsContent>
            </Tabs>
          </motion.div>
        )}
      </main>
      
      <footer className="border-t border-white/[0.04] py-6 mt-auto relative z-10">
        <div className="container mx-auto px-4 flex flex-col md:flex-row items-center justify-between gap-4 text-sm text-slate-600">
          <p>RDIP &copy; 2025</p>
          <div className="flex items-center gap-6">
            <a href="#" className="hover:text-slate-300 transition-colors">Docs</a>
            <a href="#" className="hover:text-slate-300 transition-colors">API</a>
            <a href="#" className="hover:text-slate-300 transition-colors">Status</a>
          </div>
        </div>
      </footer>
    </div>
  );
}