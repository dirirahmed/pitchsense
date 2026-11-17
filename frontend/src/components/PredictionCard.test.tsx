import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { PredictionCard, formatPercent } from './PredictionCard';

describe('PredictionCard', () => {
  it('shows a placeholder when probabilities are null', () => {
    render(<PredictionCard title="Odds" probabilities={null} />);

    expect(screen.getByText(/not available/i)).toBeInTheDocument();
  });

  it('renders home/draw/away percentages', () => {
    render(
      <PredictionCard
        title="LR"
        probabilities={{ home: 0.5, draw: 0.3, away: 0.2 }}
      />,
    );

    expect(screen.getByText('50.0%')).toBeInTheDocument();
    expect(screen.getByText('30.0%')).toBeInTheDocument();
    expect(screen.getByText('20.0%')).toBeInTheDocument();
  });
});

describe('formatPercent', () => {
  it('rounds to one decimal place and appends %', () => {
    expect(formatPercent(0.4567)).toBe('45.7%');
    expect(formatPercent(1)).toBe('100.0%');
    expect(formatPercent(0)).toBe('0.0%');
  });
});
