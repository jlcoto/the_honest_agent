// Shared accuracy-scale helpers (4 buckets)
export const BUCKETS=['correct','mostly','partly','wrong'];
export const BUCKET_LABEL={correct:'Correct',mostly:'Mostly right',partly:'Partly right',wrong:'Wrong'};
export const BUCKET_COLOR={correct:'var(--acc-correct)',mostly:'var(--acc-mostly)',partly:'var(--acc-partly)',wrong:'var(--acc-wrong)'};
export const BUCKET_TINT={correct:'var(--acc-correct-tint)',mostly:'var(--acc-mostly-tint)',partly:'var(--acc-partly-tint)',wrong:'var(--acc-wrong-tint)'};
export const BUCKET_INK={correct:'var(--acc-correct-ink)',mostly:'var(--acc-mostly-ink)',partly:'var(--acc-partly-ink)',wrong:'var(--acc-wrong-ink)'};
export function bucketOf(score){if(score==null||isNaN(score))return null;if(score>=0.95)return 'correct';if(score>=0.75)return 'mostly';if(score>=0.4)return 'partly';return 'wrong';}
export function pct(score,d){if(score==null)return '—';return (score*100).toFixed(d==null?1:d)+'%';}
