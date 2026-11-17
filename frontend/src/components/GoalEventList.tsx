import type { GoalMessage, ProbabilityMessage } from '../hooks/useReplay';

interface GoalEventListProps {
  goals: GoalMessage[];
  probabilities: ProbabilityMessage[];
  homeTeam: string;
  awayTeam: string;
}

/** Chronological list of goals with the matching probability snapshot. */
export function GoalEventList({ goals, probabilities, homeTeam, awayTeam }: GoalEventListProps) {
  if (goals.length === 0) {
    return <p className="goal-list__empty">No goals yet.</p>;
  }

  return (
    <ol className="goal-list">
      {goals.map((goal, index) => {
        const snapshot = findSnapshotForGoal(probabilities, goal);
        const scorer = goal.scoring_side === 'home' ? homeTeam : awayTeam;
        return (
          <li
            key={`${goal.minute}-${index}`}
            className={`goal-list__item ${snapshot?.clutch ? 'goal-list__item--clutch' : ''}`}
          >
            <span className="goal-list__minute">{goal.minute}'</span>
            <span className="goal-list__scorer">⚽ {scorer}</span>
            <span className="goal-list__score">
              {goal.home_score} – {goal.away_score}
            </span>
            {snapshot?.clutch ? <span className="goal-list__clutch">Clutch</span> : null}
          </li>
        );
      })}
    </ol>
  );
}

function findSnapshotForGoal(
  probabilities: ProbabilityMessage[],
  goal: GoalMessage,
): ProbabilityMessage | undefined {
  // The server emits goal then probability, so the snapshot matches on minute+score.
  return probabilities.find(
    (snapshot) =>
      snapshot.minute === goal.minute &&
      snapshot.home_score === goal.home_score &&
      snapshot.away_score === goal.away_score,
  );
}
