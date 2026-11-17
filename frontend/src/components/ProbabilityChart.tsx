import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import type { ProbabilityMessage } from '../hooks/useReplay';

interface ProbabilityChartProps {
  probabilities: ProbabilityMessage[];
}

/** Live win probability chart: home/draw/away as % over the match's minutes. */
export function ProbabilityChart({ probabilities }: ProbabilityChartProps) {
  const data = probabilities.map((snapshot) => ({
    minute: snapshot.minute,
    Home: Math.round(snapshot.home * 100),
    Draw: Math.round(snapshot.draw * 100),
    Away: Math.round(snapshot.away * 100),
  }));

  return (
    <div className="probability-chart">
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
          <XAxis dataKey="minute" domain={[0, 90]} type="number" ticks={[0, 15, 30, 45, 60, 75, 90]}>
            <label />
          </XAxis>
          <YAxis domain={[0, 100]} unit="%" />
          <Tooltip
            formatter={(value: number) => `${value}%`}
            labelFormatter={(minute: number) => `Minute ${minute}`}
          />
          <Legend />
          <Line type="monotone" dataKey="Home" stroke="#16a34a" strokeWidth={2} dot={false} isAnimationActive={false} />
          <Line type="monotone" dataKey="Draw" stroke="#6b7280" strokeWidth={2} dot={false} isAnimationActive={false} />
          <Line type="monotone" dataKey="Away" stroke="#dc2626" strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
