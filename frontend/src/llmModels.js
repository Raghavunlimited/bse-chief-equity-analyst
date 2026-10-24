/** BYO LLM model catalog — ids must match backend allow-lists. */

export const LLM_MODELS = [
  {
    id: 'openai:gpt-4o',
    provider: 'openai',
    model: 'gpt-4o',
    label: 'OpenAI · GPT-4o (best general)',
    tier: 'flagship',
  },
  {
    id: 'openai:gpt-4o-mini',
    provider: 'openai',
    model: 'gpt-4o-mini',
    label: 'OpenAI · GPT-4o mini (fast / cheap)',
    tier: 'fast',
  },
  {
    id: 'openai:o3-mini',
    provider: 'openai',
    model: 'o3-mini',
    label: 'OpenAI · o3-mini (reasoning)',
    tier: 'reasoning',
  },
  {
    id: 'anthropic:claude-opus-4-20250514',
    provider: 'anthropic',
    model: 'claude-opus-4-20250514',
    label: 'Anthropic · Claude Opus 4 (strongest)',
    tier: 'flagship',
  },
  {
    id: 'anthropic:claude-sonnet-4-20250514',
    provider: 'anthropic',
    model: 'claude-sonnet-4-20250514',
    label: 'Anthropic · Claude Sonnet 4 (balanced)',
    tier: 'balanced',
  },
  {
    id: 'anthropic:claude-3-5-haiku-20241022',
    provider: 'anthropic',
    model: 'claude-3-5-haiku-20241022',
    label: 'Anthropic · Claude 3.5 Haiku (fast)',
    tier: 'fast',
  },
  {
    id: 'anthropic:claude-3-opus-20240229',
    provider: 'anthropic',
    model: 'claude-3-opus-20240229',
    label: 'Anthropic · Claude 3 Opus (legacy flagship)',
    tier: 'flagship',
  },
];

export const DEFAULT_MODEL_ID = 'openai:gpt-4o';

export function findModel(id) {
  return LLM_MODELS.find((m) => m.id === id) || LLM_MODELS[0];
}

export function resolveModelSelection({ provider, modelId, model } = {}) {
  if (modelId) {
    const hit = findModel(modelId);
    return { provider: hit.provider, model: hit.model, modelId: hit.id };
  }
  if (model && provider) {
    const hit = LLM_MODELS.find((m) => m.provider === provider && m.model === model);
    if (hit) return { provider: hit.provider, model: hit.model, modelId: hit.id };
    return { provider, model, modelId: `${provider}:${model}` };
  }
  // Legacy: provider only
  if (provider === 'anthropic') {
    const hit = findModel('anthropic:claude-opus-4-20250514');
    return { provider: hit.provider, model: hit.model, modelId: hit.id };
  }
  const hit = findModel(DEFAULT_MODEL_ID);
  return { provider: hit.provider, model: hit.model, modelId: hit.id };
}
