import React, { useState, useEffect } from 'react';
import { Rocket, TrendingUp, Zap, Shield, ChevronRight, RefreshCw, Target, AlertTriangle, X } from 'lucide-react';

const FuturisticSectors = () => {
  const [sectors, setSectors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedSector, setSelectedSector] = useState(null);
  const [sectorPicks, setSectorPicks] = useState(null);
  const [loadingPicks, setLoadingPicks] = useState(false);

  useEffect(() => {
    fetchSectors();
  }, []);

  const fetchSectors = async () => {
    try {
      setLoading(true);
      const response = await fetch('/api/futuristic-sectors');
      if (!response.ok) throw new Error('Failed to fetch sectors');
      const data = await response.json();
      setSectors(data.sectors || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchSectorPicks = async (sectorName) => {
    setLoadingPicks(true);
    setSelectedSector(sectorName);
    setSectorPicks(null);
    
    try {
      const encodedName = encodeURIComponent(sectorName);
      const response = await fetch(`/api/futuristic-sectors/${encodedName}/picks?top_n=3`);
      if (!response.ok) throw new Error('Failed to fetch sector picks');
      const data = await response.json();
      setSectorPicks(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingPicks(false);
    }
  };

  const closePicks = () => {
    setSelectedSector(null);
    setSectorPicks(null);
  };

  const getSectorIcon = (sectorName) => {
    if (sectorName.includes('EV') || sectorName.includes('Green')) return '🔋';
    if (sectorName.includes('AI') || sectorName.includes('Data')) return '🤖';
    if (sectorName.includes('Defence')) return '🛡️';
    if (sectorName.includes('Digital') || sectorName.includes('Fintech')) return '💳';
    if (sectorName.includes('Healthcare')) return '🏥';
    if (sectorName.includes('Infrastructure')) return '🏗️';
    return '🚀';
  };

  const getSectorGradient = (index) => {
    const gradients = [
      'from-green-600 to-emerald-800',
      'from-blue-600 to-indigo-800',
      'from-orange-600 to-red-800',
      'from-purple-600 to-pink-800',
      'from-cyan-600 to-teal-800',
      'from-yellow-600 to-amber-800'
    ];
    return gradients[index % gradients.length];
  };

  const getBuyZoneColor = (zone) => {
    if (zone === 'IN ZONE') return 'text-green-400 bg-green-900/30';
    if (zone === 'BELOW ZONE') return 'text-blue-400 bg-blue-900/30';
    return 'text-orange-400 bg-orange-900/30';
  };

  const formatCurrency = (value) => {
    if (!value) return 'N/A';
    return `₹${value.toLocaleString('en-IN')}`;
  };

  if (loading) {
    return (
      <div className="bg-gray-900 rounded-xl p-6">
        <div className="flex items-center justify-center py-12">
          <RefreshCw className="animate-spin text-purple-400" size={32} />
          <span className="ml-3 text-gray-400">Loading futuristic sectors...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="futuristic-sectors bg-gray-900 rounded-xl p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-gradient-to-r from-purple-600 to-pink-600 rounded-lg">
            <Rocket size={24} className="text-white" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-white">Futuristic Sectors</h2>
            <p className="text-gray-400 text-sm">High-growth themes for 5-10 year wealth creation</p>
          </div>
        </div>
        <button
          onClick={fetchSectors}
          className="p-2 bg-gray-700 hover:bg-gray-600 rounded-lg"
        >
          <RefreshCw size={16} className="text-gray-300" />
        </button>
      </div>

      {/* Error State */}
      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 mb-4">
          <p className="text-red-400">{error}</p>
        </div>
      )}

      {/* Sector Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {sectors.map((sector, index) => (
          <div
            key={sector.name}
            className={`rounded-xl overflow-hidden cursor-pointer transform transition-all hover:scale-105 hover:shadow-xl`}
            onClick={() => fetchSectorPicks(sector.name)}
          >
            {/* Gradient Header */}
            <div className={`bg-gradient-to-r ${getSectorGradient(index)} p-4`}>
              <div className="flex items-center justify-between">
                <span className="text-3xl">{getSectorIcon(sector.name)}</span>
                <div className="bg-white/20 px-2 py-1 rounded text-white text-xs">
                  {sector.stock_count} stocks
                </div>
              </div>
              <h3 className="text-lg font-bold text-white mt-2">{sector.name}</h3>
              <p className="text-white/80 text-sm line-clamp-2">{sector.description}</p>
            </div>
            
            {/* Card Body */}
            <div className="bg-gray-800 p-4">
              <div className="flex items-center justify-between mb-3">
                <span className="text-gray-400 text-sm">Growth Potential</span>
                <span className="text-green-400 font-semibold">{sector.growth_potential}</span>
              </div>
              
              <div className="mb-3">
                <span className="text-gray-400 text-sm">Top Picks</span>
                <div className="flex gap-2 mt-1">
                  {(sector.top_picks || []).slice(0, 3).map(pick => (
                    <span key={pick} className="bg-gray-700 px-2 py-1 rounded text-white text-xs">
                      {pick}
                    </span>
                  ))}
                </div>
              </div>
              
              <div className="flex items-center text-purple-400 font-medium">
                <span>View Analysis</span>
                <ChevronRight size={16} className="ml-1" />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Sector Details Modal */}
      {selectedSector && (
        <div className="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-800 rounded-xl max-w-4xl w-full max-h-[90vh] overflow-y-auto">
            {/* Modal Header */}
            <div className="sticky top-0 bg-gray-800 border-b border-gray-700 p-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-3xl">{getSectorIcon(selectedSector)}</span>
                <h3 className="text-xl font-bold text-white">{selectedSector}</h3>
              </div>
              <button
                onClick={closePicks}
                className="p-2 hover:bg-gray-700 rounded-lg"
              >
                <X size={20} className="text-gray-400" />
              </button>
            </div>
            
            {/* Loading State */}
            {loadingPicks && (
              <div className="flex items-center justify-center py-16">
                <RefreshCw className="animate-spin text-purple-400" size={32} />
                <span className="ml-3 text-gray-400">Fetching stock analysis...</span>
              </div>
            )}
            
            {/* Sector Content */}
            {sectorPicks && !loadingPicks && (
              <div className="p-6">
                {/* Sector Overview */}
                <div className="bg-gray-700 rounded-lg p-4 mb-6">
                  <p className="text-gray-300">{sectorPicks.description}</p>
                  <div className="flex items-center gap-4 mt-3">
                    <div className="flex items-center gap-2">
                      <TrendingUp size={16} className="text-green-400" />
                      <span className="text-green-400 font-semibold">{sectorPicks.growth_potential}</span>
                    </div>
                  </div>
                </div>
                
                {/* Tailwinds */}
                <div className="mb-6">
                  <h4 className="text-white font-semibold mb-3 flex items-center gap-2">
                    <Zap size={16} className="text-yellow-400" /> Key Tailwinds
                  </h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                    {(sectorPicks.tailwinds || []).map((tailwind, i) => (
                      <div key={i} className="bg-green-900/20 border border-green-800 rounded-lg p-3 flex items-start gap-2">
                        <span className="text-green-400">✓</span>
                        <span className="text-gray-300 text-sm">{tailwind}</span>
                      </div>
                    ))}
                  </div>
                </div>
                
                {/* Risks */}
                {sectorPicks.risks && sectorPicks.risks.length > 0 && (
                  <div className="mb-6">
                    <h4 className="text-white font-semibold mb-3 flex items-center gap-2">
                      <AlertTriangle size={16} className="text-orange-400" /> Key Risks
                    </h4>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                      {sectorPicks.risks.map((risk, i) => (
                        <div key={i} className="bg-orange-900/20 border border-orange-800 rounded-lg p-3 flex items-start gap-2">
                          <span className="text-orange-400">⚠</span>
                          <span className="text-gray-300 text-sm">{risk}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                
                {/* Key Metrics */}
                {sectorPicks.key_metrics && Object.keys(sectorPicks.key_metrics).length > 0 && (
                  <div className="mb-6">
                    <h4 className="text-white font-semibold mb-3">Market Opportunity</h4>
                    <div className="grid grid-cols-3 gap-4">
                      {Object.entries(sectorPicks.key_metrics).map(([key, value]) => (
                        <div key={key} className="bg-gray-700 rounded-lg p-3 text-center">
                          <p className="text-gray-400 text-xs capitalize">{key.replace(/_/g, ' ')}</p>
                          <p className="text-white font-bold mt-1">{value}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                
                {/* Top Picks */}
                <div>
                  <h4 className="text-white font-semibold mb-3 flex items-center gap-2">
                    <Target size={16} className="text-purple-400" /> Top 3 Picks
                  </h4>
                  <div className="space-y-4">
                    {(sectorPicks.top_picks || []).map((stock, index) => (
                      <div key={stock.symbol} className="bg-gray-700 rounded-xl p-4">
                        {stock.error ? (
                          <div className="flex items-center gap-2 text-gray-400">
                            <span className="text-lg font-bold">{stock.symbol}</span>
                            <span className="text-sm">- Data unavailable</span>
                          </div>
                        ) : (
                          <>
                            <div className="flex items-center justify-between mb-3">
                              <div className="flex items-center gap-3">
                                <div className="w-8 h-8 bg-purple-600 rounded-full flex items-center justify-center text-white font-bold">
                                  {index + 1}
                                </div>
                                <div>
                                  <h5 className="text-lg font-bold text-white">{stock.symbol}</h5>
                                  <p className="text-gray-400 text-sm">{stock.company_name}</p>
                                </div>
                              </div>
                              <div className="text-right">
                                <p className="text-white font-bold text-xl">{formatCurrency(stock.current_price)}</p>
                                <p className="text-gray-400 text-sm">Mkt Cap: ₹{stock.market_cap_cr?.toLocaleString()} Cr</p>
                              </div>
                            </div>
                            
                            {/* Quick Metrics */}
                            <div className="grid grid-cols-4 gap-3 mb-3">
                              <div className="bg-gray-800 rounded-lg p-2 text-center">
                                <p className="text-gray-400 text-xs">ROE</p>
                                <p className="text-white font-semibold">{stock.metrics?.roe?.toFixed(1) || 'N/A'}%</p>
                              </div>
                              <div className="bg-gray-800 rounded-lg p-2 text-center">
                                <p className="text-gray-400 text-xs">Growth</p>
                                <p className="text-green-400 font-semibold">{stock.metrics?.revenue_growth?.toFixed(1) || 'N/A'}%</p>
                              </div>
                              <div className="bg-gray-800 rounded-lg p-2 text-center">
                                <p className="text-gray-400 text-xs">P/E</p>
                                <p className="text-white font-semibold">{stock.metrics?.pe_ratio?.toFixed(1) || 'N/A'}</p>
                              </div>
                              <div className="bg-gray-800 rounded-lg p-2 text-center">
                                <p className="text-gray-400 text-xs">Score</p>
                                <p className="text-purple-400 font-semibold">{stock.score}/100</p>
                              </div>
                            </div>
                            
                            {/* Buy Zone */}
                            {stock.buy_zone && (
                              <div className="flex items-center justify-between bg-gray-800 rounded-lg p-3">
                                <div>
                                  <p className="text-gray-400 text-sm">Buy Zone</p>
                                  <p className="text-white">
                                    {formatCurrency(stock.buy_zone.low)} - {formatCurrency(stock.buy_zone.high)}
                                  </p>
                                </div>
                                <span className={`px-3 py-1 rounded-full text-sm font-semibold ${getBuyZoneColor(stock.buy_zone.current_vs_zone)}`}>
                                  {stock.buy_zone.current_vs_zone}
                                </span>
                              </div>
                            )}
                            
                            {/* 52 Week Range */}
                            <div className="mt-3">
                              <div className="flex justify-between text-xs text-gray-400 mb-1">
                                <span>52W Low: {formatCurrency(stock['52_week_low'])}</span>
                                <span>52W High: {formatCurrency(stock['52_week_high'])}</span>
                              </div>
                              <div className="w-full bg-gray-600 rounded-full h-2">
                                <div 
                                  className="bg-purple-500 h-2 rounded-full"
                                  style={{
                                    width: `${Math.min(100, Math.max(0, 
                                      ((stock.current_price - stock['52_week_low']) / 
                                       (stock['52_week_high'] - stock['52_week_low'])) * 100
                                    ))}%`
                                  }}
                                />
                              </div>
                            </div>
                          </>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
                
                {/* All Stocks in Sector */}
                {sectorPicks.all_stocks && (
                  <div className="mt-6">
                    <h4 className="text-white font-semibold mb-2">All Stocks in Sector</h4>
                    <div className="flex flex-wrap gap-2">
                      {sectorPicks.all_stocks.map(symbol => (
                        <span key={symbol} className="bg-gray-700 px-2 py-1 rounded text-gray-300 text-sm hover:bg-gray-600 cursor-pointer">
                          {symbol}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default FuturisticSectors;
