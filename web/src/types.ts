export interface Source {
  id: string;
  title: string;
  excerpt: string;
  score: number;
}
export interface Memory {
  id: string;
  key: string;
  value: string;
  kind: string;
  active: boolean;
  supersededBy?: string;
}
export interface Attempt {
  number: number;
  html: string;
  errors: string[];
  browserStatus: string;
  screenshot?: string;
  durationMs: number;
}
export interface Step { action: string; target: string; value?: string }
export interface Run {
  workflow?: string;
  calls?: number;
  steps?: Step[];
  plan?: {summary?: string};
  contractHash?: string;
  resumable?: boolean;
  id: string;
  prompt: string;
  mode: string;
  model: string;
  status: string;
  createdAt: string;
  maxRepairs: number;
  durationMs: number;
  inputTokens: number;
  outputTokens: number;
  usageKnown: boolean;
  estimatedCost?: number;
  error?: string;
  attempts: Attempt[];
  memorySources: Source[];
  events: { at: string; stage: string; message: string }[];
}
export interface Project {
  id: string;
  name: string;
  memories: Memory[];
  documents: { id: string; title: string; content: string }[];
  runs: Run[];
  selectedRunId?: string;
}
export interface Config {
  aiEnabled: boolean;
  mode: string;
  modelConfigured: boolean;
  browserValidation: boolean;
  liveAccessRequired: boolean;
}
