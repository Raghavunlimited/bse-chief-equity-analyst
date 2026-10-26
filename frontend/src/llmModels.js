/** BYO LLM model catalog — cloud ids match backend allow-lists; local uses safe name pattern. */

export const LLM_MODELS = [
  {
    id: 'local:llama3.2',
    provider: 'local',
    model: 'llama3.2',
    label: 'Local · Ollama/LM Studio · llama3.2 (no cloud key)',
    tier: 'local',
  },
  {
    id: 'local:mistral',
    provider: 'local',
    model: 'mistral',
    label: 'Local · Ollama/LM Studio · mistral',
    tier: 'local',
  },
  {
    id: 'local:qwen2.5',
    provider: 'local',
    model: 'qwen2.5',
    label: 'Local · Ollama/LM Studio · qwen2.5',
    tier: 'local',
  },
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
export const LOCAL_CUSTOM_PREFIX = 'local:custom:';

/** Safe local model id — mirrors backend `_LOCAL_MODEL_RE`. */
export function isSafeLocalModelId(name) {
  return /^[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,79}$/.test(String(name || '').trim());
}

export function findModel(id) {
  if (String(id || '').startsWith(LOCAL_CUSTOM_PREFIX)) {
    const model = String(id).slice(LOCAL_CUSTOM_PREFIX.length);
    return {
      id,
      provider: 'local',
      model,
      label: `Local · custom · ${model}`,
      tier: 'local',
    };
  }
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
    if (provider === 'local' && isSafeLocalModelId(model)) {
      return {
        provider: 'local',
        model: String(model).trim(),
        modelId: `${LOCAL_CUSTOM_PREFIX}${String(model).trim()}`,
      };
    }
    return { provider, model, modelId: `${provider}:${model}` };
  }
  // Legacy: provider only
  if (provider === 'local') {
    const hit = findModel('local:llama3.2');
    return { provider: hit.provider, model: hit.model, modelId: hit.id };
  }
  if (provider === 'anthropic') {
    const hit = findModel('anthropic:claude-opus-4-20250514');
    return { provider: hit.provider, model: hit.model, modelId: hit.id };
  }
  const hit = findModel(DEFAULT_MODEL_ID);
  return { provider: hit.provider, model: hit.model, modelId: hit.id };
}
