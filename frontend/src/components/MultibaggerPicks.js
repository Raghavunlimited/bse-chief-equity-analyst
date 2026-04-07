import React, { useState } from 'react';
import { TrendingUp, Award, Shield, DollarSign, Target, ChevronDown, ChevronUp, RefreshCw, Info, AlertTriangle } from 'lucide-react';
import { screenerAPI } from '../services/api';

const MultibaggerPicks = () => {
  const [candidates, setCandidates] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState({});
  const [stats, setStats] = useState(null);
  const [methodology, setMethodology] = useState(null);
  const [showMethodology, setShowMethodology] = useState(false);

  const runScreener = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/screener/multibagger?top_n=10&min_score=45', {
        method: 'POST'
      });
      if (!response.ok) throw new Error('Failed to fetch data');
      const data = await response.json();
      setCandidates(data.candidates || []);
      setStats(data.stats);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchMethodology = async () => {
    try {
      const response = await fetch('/api/screener/multibagger/methodology');
      const data = await response.json();
      setMethodology(data);
      setShowMethodology(true);
    } catch (err) {
      console.error('Error fetching methodology:', err);
    }
  };

  const toggleExpand = (symbol) => {
    setExpanded(prev => ({ ...prev, [symbol]: !prev[symbol] }));
  };

  const getSignalColor = (signal) => {
    switch (signal) {
      case 'STRONG BUY': return 'bg-green-600';
      case 'BUY': return 'bg-green-500';
      case 'HOLD/ACCUMULATE': return 'bg-yellow-500';
      case 'WATCH': return 'bg-orange-500';
      default: return 'bg-red-500';
    }
  };

  const getScoreColor = (score) => {
    if (score >= 75) return 'text-green-400';
    if (score >= 60) return 'text-green-300';
    if (score >= 45) return 'text-yellow-400';
    return 'text-red-400';
  };

  const formatCurrency = (value) => {
    if (!value) return 'N/A';
    return `₹${value.toLocaleString('en-IN')}`;
  };

  const formatPercent = (value) => {
    if (value === null || value === undefined) return 'N/A';
    return `${value.toFixed(1)}%`;
  };

  return (
    <div className="multibagger-picks bg-gray-900 rounded-xl p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-purple-600 rounded-lg">
            <TrendingUp size={24} className="text-white" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-white">Multibagger Picks</h2>
            <p className="text-gray-400 text-sm">Long-term wealth creation (3-5 years)</p>
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={fetchMethodology}
            className="px-3 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg flex items-center gap-2"
          >
            <Info size={16} />
            How it works
          </button>
          <button
            onClick={runScreener}
            disabled={loading}
            className="px-4 py-2 bg-purple-600 hover:bg-purple-500 text-white rounded-lg flex items-center gap-2 disabled:opacity-50"
          >
            {loading ? <RefreshCw className="animate-spin" size={16} /> : <Target size={16} />}
            {loading ? 'Analyzing...' : 'Find Multibaggers'}
          </button>
        </div>
      </div>

      {/* Methodology Modal */}
      {showMethodology && methodology && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-800 rounded-xl p-6 max-w-2xl max-h-[80vh] overflow-y-auto">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-xl font-bold text-white">Multibagger Methodology</h3>
              <button onClick={() => setShowMethodology(false)} className="text-gray-400 hover:text-white">✕</button>
            </div>
            
            <div className="space-y-4">
              <div>
                <h4 className="text-purple-400 font-semibold mb-2">Objective</h4>
                <p className="text-gray-300">{methodology.objective}</p>
              </div>
              
              <div>
                <h4 className="text-purple-400 font-semibold mb-2">Scoring System (100 points)</h4>
                <div className="grid grid-cols-2 gap-3">
                  {Object.entries(methodology.scoring || {}).map(([key, val]) => (
                    <div key={key} className="bg-gray-700 p-3 rounded-lg">
                      <div className="flex justify-between">
                        <span className="text-white capitalize">{key}</span>
                        <span className="text-purple-400">{val.weight} pts</span>
                      </div>
                      <p className="text-gray-400 text-sm mt-1">{val.criteria}</p>
                    </div>
                  ))}
                </div>
              </div>
              
              <div>
                <h4 className="text-purple-400 font-semibold mb-2">Signal Interpretation</h4>
                <div className="space-y-2">
                  {Object.entries(methodology.signals || {}).map(([signal, desc]) => (
                    <div key={signal} className="flex gap-2">
                      <span className={`px-2 py-1 rounded text-xs ${getSignalColor(signal)} text-white`}>{signal}</span>
                      <span className="text-gray-300">{desc}</span>
                    </div>
                  ))}
                </div>
              </div>
              
              <div className="bg-yellow-900/30 border border-yellow-700 rounded-lg p-4">
                <div className="flex gap-2 items-start">
                  <AlertTriangle className="text-yellow-500 flex-shrink-0" size={20} />
                  <div>
                    <p className="text-yellow-400 font-semibold">Risk Warnings</p>
                    <ul className="text-gray-300 text-sm mt-1 space-y-1">
                      {(methodology.risk_warnings || []).map((warning, i) => (
                        <li key={i}>• {warning}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Error State */}
      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 mb-4">
          <p className="text-red-400">{error}</p>
        </div>
      )}

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="bg-gray-800 rounded-lg p-4 text-center">
            <p className="text-gray-400 text-sm">Stocks Screened</p>
            <p className="text-2xl font-bold text-white">{stats.total_screened}</p>
          </div>
          <div className="bg-gray-800 rounded-lg p-4 text-center">
            <p className="text-gray-400 text-sm">Qualified</p>
            <p className="text-2xl font-bold text-green-400">{stats.qualified}</p>
          </div>
          <div className="bg-gray-800 rounded-lg p-4 text-center">
            <p className="text-gray-400 text-sm">Avg Score</p>
            <p className="text-2xl font-bold text-purple-400">{stats.avg_score?.toFixed(0)}/100</p>
          </div>
        </div>
      )}

      {/* Empty State */}
      {!loading && candidates.length === 0 && (
        <div className="text-center py-12">
          <TrendingUp size={48} className="text-gray-600 mx-auto mb-4" />
          <p className="text-gray-400">Click "Find Multibaggers" to discover long-term investment opportunities</p>
          <p className="text-gray-500 text-sm mt-2">Analysis may take 30-60 seconds</p>
        </div>
      )}

      {/* Candidates List */}
      <div className="space-y-4">
        {candidates.map((stock, index) => (
          <div key={stock.symbol} className="bg-gray-800 rounded-xl overflow-hidden">
            {/* Stock Header */}
            <div 
              className="p-4 cursor-pointer hover:bg-gray-750"
              onClick={() => toggleExpand(stock.symbol)}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className="w-8 h-8 bg-purple-600 rounded-full flex items-center justify-center text-white font-bold">
                    {index + 1}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-lg font-bold text-white">{stock.symbol}</h3>
                      <span className={`px-2 py-0.5 rounded text-xs text-white ${getSignalColor(stock.signal)}`}>
                        {stock.signal}
                      </span>
                    </div>
                    <p className="text-gray-400 text-sm">{stock.company_name}</p>
                  </div>
                </div>
                
                <div className="flex items-center gap-6">
                  <div className="text-right">
                    <p className="text-gray-400 text-sm">Price</p>
                    <p className="text-white font-bold">{formatCurrency(stock.current_price)}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-gray-400 text-sm">Score</p>
                    <p className={`text-2xl font-bold ${getScoreColor(stock.score)}`}>{stock.score}</p>
                  </div>
                  {expanded[stock.symbol] ? <ChevronUp className="text-gray-400" /> : <ChevronDown className="text-gray-400" />}
                </div>
              </div>
              
              {/* Quick Metrics */}
              <div className="grid grid-cols-4 gap-4 mt-4">
                <div className="bg-gray-700 rounded-lg p-2 text-center">
                  <p className="text-gray-400 text-xs">ROE</p>
                  <p className="text-white font-semibold">{formatPercent(stock.key_metrics?.roe)}</p>
                </div>
                <div className="bg-gray-700 rounded-lg p-2 text-center">
                  <p className="text-gray-400 text-xs">Growth</p>
                  <p className="text-green-400 font-semibold">{formatPercent(stock.key_metrics?.revenue_growth)}</p>
                </div>
                <div className="bg-gray-700 rounded-lg p-2 text-center">
                  <p className="text-gray-400 text-xs">P/E</p>
                  <p className="text-white font-semibold">{stock.key_metrics?.pe_ratio?.toFixed(1) || 'N/A'}</p>
                </div>
                <div className="bg-gray-700 rounded-lg p-2 text-center">
                  <p className="text-gray-400 text-xs">D/E</p>
                  <p className="text-white font-semibold">{stock.key_metrics?.debt_to_equity?.toFixed(2) || 'N/A'}</p>
                </div>
              </div>
            </div>
            
            {/* Expanded Details */}
            {expanded[stock.symbol] && (
              <div className="border-t border-gray-700 p-4 bg-gray-850">
                {/* Score Breakdown */}
                <div className="mb-4">
                  <h4 className="text-white font-semibold mb-2 flex items-center gap-2">
                    <Award size={16} className="text-purple-400" /> Score Breakdown
                  </h4>
                  <div className="grid grid-cols-5 gap-2">
                    {Object.entries(stock.score_breakdown || {}).map(([key, data]) => (
                      <div key={key} className="bg-gray-700 rounded-lg p-2 text-center">
                        <p className="text-gray-400 text-xs capitalize">{key}</p>
                        <p className="text-white font-semibold">{data.score}/{data.max}</p>
                      </div>
                    ))}
                  </div>
                </div>
                
                {/* Investment Thesis */}
                {stock.investment_thesis && (
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <h4 className="text-green-400 font-semibold mb-2 flex items-center gap-2">
                        <Shield size={16} /> Pros
                      </h4>
                      <ul className="space-y-1">
                        {(stock.investment_thesis.pros || []).map((pro, i) => (
                          <li key={i} className="text-gray-300 text-sm flex items-start gap-2">
                            <span className="text-green-400">✓</span> {pro}
                          </li>
                        ))}
                      </ul>
                    </div>
                    <div>
                      <h4 className="text-red-400 font-semibold mb-2 flex items-center gap-2">
                        <AlertTriangle size={16} /> Cons
                      </h4>
                      <ul className="space-y-1">
                        {(stock.investment_thesis.cons || []).map((con, i) => (
                          <li key={i} className="text-gray-300 text-sm flex items-start gap-2">
                            <span className="text-red-400">✗</span> {con}
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                )}
                
                {/* Target & Recommendation */}
                {stock.investment_thesis && (
                  <div className="mt-4 bg-purple-900/30 border border-purple-700 rounded-lg p-4">
                    <div className="flex justify-between items-center">
                      <div>
                        <p className="text-gray-400 text-sm">3-Year Target</p>
                        <p className="text-2xl font-bold text-purple-400">
                          {stock.investment_thesis.target_price_3y 
                            ? formatCurrency(stock.investment_thesis.target_price_3y)
                            : 'N/A'}
                        </p>
                        {stock.investment_thesis.potential_upside && (
                          <p className="text-green-400 text-sm">
                            +{stock.investment_thesis.potential_upside}% potential upside
                          </p>
                        )}
                      </div>
                      <div className="text-right">
                        <p className="text-gray-400 text-sm">Recommendation</p>
                        <p className="text-white">{stock.recommendation}</p>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default MultibaggerPicks;
