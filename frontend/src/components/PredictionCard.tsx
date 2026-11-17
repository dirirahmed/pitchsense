import type { ProbabilityTriple } from '../api/matches';

interface PredictionCardProps {
  title: string;
  description?: string;
  probabilities: ProbabilityTriple | null;
  highlight?: boolean;
}

/** Shows one source's home/draw/away probabilities as a stacked bar. */
export function PredictionCard({
  title,
  description,
  probabilities,
  highlight,
}: PredictionCardProps) {
  if (!probabilities) {
    return (
      <section className={`prediction-card ${highlight ? 'prediction-card--highlight' : ''}`}>
        <h3>{title}</h3>
        {description ? <p className="prediction-card__description">{description}</p> : null}
        <p className="prediction-card__empty">Not available for this match</p>
      </section>
    );
  }

  const total = probabilities.home + probabilities.draw + probabilities.away;
  const home = (probabilities.home / total) * 100;
  const draw = (probabilities.draw / total) * 100;
  const away = (probabilities.away / total) * 100;

  return (
    <section
      className={`prediction-card ${highlight ? 'prediction-card--highlight' : ''}`}
      aria-label={title}
    >
      <h3>{title}</h3>
      {description ? <p className="prediction-card__description">{description}</p> : null}
      <div className="prediction-card__bar" role="img" aria-label="Probability distribution">
        <div className="prediction-card__bar-home" style={{ width: `${home}%` }} />
        <div className="prediction-card__bar-draw" style={{ width: `${draw}%` }} />
        <div className="prediction-card__bar-away" style={{ width: `${away}%` }} />
      </div>
      <dl className="prediction-card__legend">
        <div>
          <dt>Home</dt>
          <dd>{formatPercent(probabilities.home)}</dd>
        </div>
        <div>
          <dt>Draw</dt>
          <dd>{formatPercent(probabilities.draw)}</dd>
        </div>
        <div>
          <dt>Away</dt>
          <dd>{formatPercent(probabilities.away)}</dd>
        </div>
      </dl>
    </section>
  );
}

export function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}
