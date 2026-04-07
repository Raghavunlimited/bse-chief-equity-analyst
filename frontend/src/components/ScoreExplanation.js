import React, { useState, useEffect } from 'react';
import { X, Info, TrendingUp, Zap, Target, BarChart2, Activity } from 'lucide-react';
import { screenerAPI } from '../services/api';

function ScoreExplanation({ onClose }) {
  const [explanation, setExplanation] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchExplanation();
  }, []);

  const fetchExplanation = async () => {
    try {
      const data = await screenerAPI.getScoreExplanation();
      setExplanation(data);
    } catch (err) {
      console.error('Failed to fetch score explanation:', err);
    } finally {
      setLoading(false);
    }
  };

  const getCategoryIcon = (category) => {
    const cat = category.toLowerCase();
    if (cat.includes('trend')) return <TrendingUp size={20} />;
    if (cat.includes('momentum')) return <Zap size={20} />;
    if (cat.includes('breakout')) return <Target size={20} />;
    if (cat.includes('volume')) return <BarChart2 size={20} />;
    if (cat.includes('volatility')) return <Activity size={20} />;
    return <Info size={20} />;
  };

  const getCategoryColor = (category) => {
    const cat = category.toLowerCase();
    if (cat.includes('trend')) return '#3b82f6';
    if (cat.includes('momentum')) return '#f59e0b';
    if (cat.includes('breakout')) return '#22c55e';
    if (cat.includes('volume')) return '#8b5cf6';
    if (cat.includes('volatility')) return '#ec4899';
    return '#6b7280';
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2><Info size={24} /> How Scores Are Calculated</h2>
          <button className="modal-close" onClick={onClose}><X size={24} /></button>
        </div>

        {loading ? (
          <div className="loading">Loading...</div>
        ) : explanation ? (
          <div className="score-explanation">
            <div className="explanation-intro">
              <p>Stocks are scored on {explanation.total_points || explanation.max_score} factors that indicate swing trading potential.</p>
              <div className="max-score-badge">
                Maximum Score: <strong>{explanation.total_points || explanation.max_score} points</strong>
              </div>
            </div>

            <div className="categories-list">
              {explanation.categories && explanation.categories.map((category, catIdx) => (
                <div
                  key={catIdx}
                  className="category-card"
                  style={{ borderLeftColor: getCategoryColor(category.name) }}
                >
                  <div className="category-header">
                    <span style={{ color: getCategoryColor(category.name) }}>
                      {getCategoryIcon(category.name)}
                    </span>
                    <h3>{category.name}</h3>
                    <span className="category-points">{category.max_points} pts</span>
                  </div>
                  <div className="criteria-list">
                    {category.factors && category.factors.map((factor, idx) => (
                      <div key={idx} className="criterion-item">
                        <span className="criterion-name">{factor.name}</span>
                        <span className="criterion-condition">{factor.condition}</span>
                        <span className="criterion-points">+{factor.points}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            <div className="scoring-notes">
              <h4>Scoring Guidelines</h4>
              <ul>
                <li><strong>15+ points:</strong> Strong setup - consider for immediate entry</li>
                <li><strong>10-14 points:</strong> Moderate setup - monitor for confirmation</li>
                <li><strong>Below 10:</strong> Weak setup - requires more patience</li>
              </ul>
              <p className="disclaimer">
                Note: Scores are based on technical analysis only. Always do your own due diligence
                and consider fundamental factors before trading.
              </p>
            </div>
          </div>
        ) : (
          <div className="error">Failed to load explanation</div>
        )}
      </div>
    </div>
  );
}

export default ScoreExplanation;
