import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { GoalMessage, ProbabilityMessage } from '../hooks/useReplay';

import { GoalEventList } from './GoalEventList';

const goals: GoalMessage[] = [
  { type: 'goal', minute: 18, scoring_side: 'home', home_score: 1, away_score: 0 },
  { type: 'goal', minute: 75, scoring_side: 'away', home_score: 1, away_score: 1 },
];

const probabilities: ProbabilityMessage[] = [
  {
    type: 'probability',
    minute: 18,
    home_score: 1,
    away_score: 0,
    home: 0.75,
    draw: 0.15,
    away: 0.10,
    clutch: true,
  },
  {
    type: 'probability',
    minute: 75,
    home_score: 1,
    away_score: 1,
    home: 0.30,
    draw: 0.45,
    away: 0.25,
    clutch: true,
  },
];

describe('GoalEventList', () => {
  it('shows an empty state before any goals', () => {
    render(
      <GoalEventList
        goals={[]}
        probabilities={[]}
        homeTeam="Arsenal"
        awayTeam="Chelsea"
      />,
    );

    expect(screen.getByText(/no goals yet/i)).toBeInTheDocument();
  });

  it('renders one entry per goal with the scoring team', () => {
    render(
      <GoalEventList
        goals={goals}
        probabilities={probabilities}
        homeTeam="Arsenal"
        awayTeam="Chelsea"
      />,
    );

    expect(screen.getByText(/Arsenal/)).toBeInTheDocument();
    expect(screen.getByText(/Chelsea/)).toBeInTheDocument();
    // Both goals landed with clutch snapshots in the fixture.
    expect(screen.getAllByText(/Clutch/)).toHaveLength(2);
  });
});
