import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import SettingsDrawer, {
  LLM_PROVIDER_STORAGE,
  LLM_MODEL_STORAGE,
} from './SettingsDrawer';
import { LLM_MODELS } from '../llmModels';
import { deskAPI } from '../services/api';

jest.mock('../services/api', () => ({
  deskAPI: {
    llmVaultStatus: jest.fn(() =>
      Promise.resolve({ data: { configured: false } }),
    ),
    llmVaultPut: jest.fn(() =>
      Promise.resolve({
        data: { configured: true, provider: 'openai', model: 'gpt-4o' },
      }),
    ),
    llmVaultDelete: jest.fn(() =>
      Promise.resolve({ data: { ok: true, configured: false } }),
    ),
  },
}));

describe('SettingsDrawer', () => {
  beforeEach(() => {
    localStorage.clear();
    deskAPI.llmVaultStatus.mockReset();
    deskAPI.llmVaultPut.mockReset();
    deskAPI.llmVaultDelete.mockReset();
    deskAPI.llmVaultStatus.mockResolvedValue({ data: { configured: false } });
    deskAPI.llmVaultPut.mockResolvedValue({
      data: { configured: true, provider: 'openai', model: 'gpt-4o' },
    });
    deskAPI.llmVaultDelete.mockResolvedValue({
      data: { ok: true, configured: false },
    });
  });

  it('shows model options including Opus', async () => {
    render(<SettingsDrawer open onClose={jest.fn()} onSaved={jest.fn()} />);
    const select = await screen.findByLabelText(/llm model/i);
    const optionTexts = Array.from(select.options).map((o) => o.textContent);
    expect(optionTexts.length).toBe(LLM_MODELS.length);
    expect(optionTexts.some((t) => /opus/i.test(t))).toBe(true);
  });

  it('Save puts key to server vault and does not keep it in localStorage', async () => {
    const onClose = jest.fn();
    const onSaved = jest.fn();

    render(<SettingsDrawer open onClose={onClose} onSaved={onSaved} />);

    fireEvent.change(await screen.findByLabelText(/llm api key/i), {
      target: { value: 'sk-test-key-12345' },
    });

    const opus = LLM_MODELS.find((m) => /opus/i.test(m.label));
    expect(opus).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/llm model/i), {
      target: { value: opus.id },
    });

    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

    await waitFor(() => {
      expect(deskAPI.llmVaultPut).toHaveBeenCalled();
    });
    const body = deskAPI.llmVaultPut.mock.calls[0][0];
    expect(body.api_key).toBe('sk-test-key-12345');
    expect(localStorage.getItem('swing_desk_llm_key')).toBeNull();
    expect(localStorage.getItem(LLM_PROVIDER_STORAGE)).toBeTruthy();
    expect(localStorage.getItem(LLM_MODEL_STORAGE)).toBeTruthy();
  });
});
