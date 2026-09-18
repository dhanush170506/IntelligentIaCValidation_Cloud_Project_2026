/** Severity / status visual mappings shared by badges, tables and reports. */

export const SEVERITY_ORDER = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO'];

export const SEVERITY_STYLES = {
  CRITICAL: {
    label: 'Critical',
    text: 'text-rose-300',
    bg: 'bg-rose-500/10',
    border: 'border-rose-500/40',
    dot: 'bg-rose-400',
  },
  HIGH: {
    label: 'High',
    text: 'text-orange-300',
    bg: 'bg-orange-500/10',
    border: 'border-orange-500/40',
    dot: 'bg-orange-400',
  },
  MEDIUM: {
    label: 'Medium',
    text: 'text-amber-300',
    bg: 'bg-amber-500/10',
    border: 'border-amber-500/40',
    dot: 'bg-amber-400',
  },
  LOW: {
    label: 'Low',
    text: 'text-sky-300',
    bg: 'bg-sky-500/10',
    border: 'border-sky-500/40',
    dot: 'bg-sky-400',
  },
  INFO: {
    label: 'Info',
    text: 'text-slate-300',
    bg: 'bg-slate-500/10',
    border: 'border-slate-500/40',
    dot: 'bg-slate-400',
  },
};

export function normalizeSeverity(raw) {
  const value = String(raw || '').toUpperCase();
  if (SEVERITY_STYLES[value]) return value;
  if (value === 'WARNING' || value === 'WARN') return 'MEDIUM';
  if (value === 'ERROR' || value === 'FAIL') return 'HIGH';
  return 'INFO';
}

export const STATUS_STYLES = {
  PASS: {
    label: 'Pass',
    text: 'text-emerald-300',
    bg: 'bg-emerald-500/10',
    border: 'border-emerald-500/40',
    dot: 'bg-emerald-400',
  },
  FAIL: {
    label: 'Fail',
    text: 'text-rose-300',
    bg: 'bg-rose-500/10',
    border: 'border-rose-500/40',
    dot: 'bg-rose-400',
  },
  REVIEW_REQUIRED: {
    label: 'Review Required',
    text: 'text-amber-300',
    bg: 'bg-amber-500/10',
    border: 'border-amber-500/40',
    dot: 'bg-amber-400',
  },
  COMPLETED: {
    label: 'Completed',
    text: 'text-emerald-300',
    bg: 'bg-emerald-500/10',
    border: 'border-emerald-500/40',
    dot: 'bg-emerald-400',
  },
  RUNNING: {
    label: 'Running',
    text: 'text-sky-300',
    bg: 'bg-sky-500/10',
    border: 'border-sky-500/40',
    dot: 'bg-sky-400',
  },
  BLOCKED: {
    label: 'Blocked',
    text: 'text-rose-300',
    bg: 'bg-rose-500/10',
    border: 'border-rose-500/40',
    dot: 'bg-rose-400',
  },
  APPROVED: {
    label: 'Approved',
    text: 'text-emerald-300',
    bg: 'bg-emerald-500/10',
    border: 'border-emerald-500/40',
    dot: 'bg-emerald-400',
  },
};

export function normalizeStatus(raw) {
  // Unknown statuses (e.g. ERROR) are returned as-is so the badge can render
  // the raw value plainly instead of mislabelling it as a known state.
  return String(raw || '').toUpperCase().replace(/[\s-]+/g, '_');
}

/** Human-friendly agent names for the structured agent_type values. */
const AGENT_LABELS = {
  SYNTAX_VALIDATION: 'Syntax Agent',
  SECURITY_VALIDATION: 'Security Agent',
  DEPLOYMENT_VALIDATION: 'Deployment Agent',
  DRIFT_DETECTION: 'Drift Agent',
  COST_ANALYSIS: 'Cost Agent',
  EVIDENCE: 'Evidence Agent',
};

export function agentLabel(agentType) {
  const key = String(agentType || '').toUpperCase();
  if (AGENT_LABELS[key]) return AGENT_LABELS[key];
  const words = key.split('_').filter(Boolean);
  if (words.length === 0) return 'Unknown Agent';
  return `${words[0][0]}${words.slice(1).join(' ').toLowerCase()}`.replace(/^./, (c) =>
    c.toUpperCase()
  );
}

/** Recommendation category buckets for grouping. */
export const RECOMMENDATION_CATEGORIES = [
  'SECURITY',
  'RELIABILITY',
  'DRIFT',
  'COST',
  'DEPLOYMENT',
];

export function normalizeRecommendationCategory(raw) {
  const value = String(raw || '').toUpperCase();
  if (RECOMMENDATION_CATEGORIES.includes(value)) return value;
  return 'OTHER';
}

export const RECOMMENDATION_CATEGORY_LABELS = {
  SECURITY: 'Security',
  RELIABILITY: 'Reliability',
  DRIFT: 'Drift',
  COST: 'Cost',
  DEPLOYMENT: 'Deployment',
  OTHER: 'Other',
};
