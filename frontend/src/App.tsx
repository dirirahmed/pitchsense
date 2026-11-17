import { Route, Routes } from 'react-router-dom';

import './App.css';
import { MatchListPage } from './pages/MatchListPage';
import { MatchPage } from './pages/MatchPage';

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<MatchListPage />} />
      <Route path="/match/:id" element={<MatchPage />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}

function NotFound() {
  return (
    <main className="match-page">
      <p className="placeholder">Not found.</p>
    </main>
  );
}
