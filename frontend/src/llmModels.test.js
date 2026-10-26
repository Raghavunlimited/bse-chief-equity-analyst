import { DEFAULT_MODEL_ID, LLM_MODELS, findModel, resolveModelSelection } from './llmModels';

describe('llmModels catalog', () => {
  test('includes Claude Opus and GPT-4o', () => {
    const ids = LLM_MODELS.map((m) => m.id);
    expect(ids.some((id) => id.includes('opus'))).toBe(true);
    expect(ids.some((id) => id.includes('gpt-4o'))).toBe(true);
    expect(ids.some((id) => id.includes('sonnet'))).toBe(true);
  });

  test('default is a flagship OpenAI model', () => {
    const hit = findModel(DEFAULT_MODEL_ID);
    expect(hit.provider).toBe('openai');
    expect(hit.model).toMatch(/gpt-4o/);
  });

  test('resolveModelSelection prefers modelId', () => {
    const r = resolveModelSelection({
      modelId: 'anthropic:claude-opus-4-20250514',
    });
    expect(r.provider).toBe('anthropic');
    expect(r.model).toContain('opus');
  });

  test('legacy anthropic provider maps to Opus', () => {
    const r = resolveModelSelection({ provider: 'anthropic' });
    expect(r.model).toContain('opus');
  });

  test('local catalog and custom model resolve safely', () => {
    const ids = LLM_MODELS.map((m) => m.id);
    expect(ids.some((id) => id.startsWith('local:'))).toBe(true);
    const r = resolveModelSelection({ modelId: 'local:llama3.2' });
    expect(r.provider).toBe('local');
    expect(r.model).toBe('llama3.2');
    const custom = resolveModelSelection({
      provider: 'local',
      model: 'llama3.2:latest',
    });
    expect(custom.provider).toBe('local');
    expect(custom.model).toBe('llama3.2:latest');
  });
});
