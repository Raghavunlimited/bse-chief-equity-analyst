import React, { useState, useEffect } from 'react';
import { Calendar, ChevronDown } from 'lucide-react';
import { screenerAPI } from '../services/api';

function DateSelector({ selectedDate, onDateChange }) {
  const [dates, setDates] = useState([]);
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchAvailableDates();
  }, []);

  const fetchAvailableDates = async () => {
    try {
      setLoading(true);
      const data = await screenerAPI.getAvailableDates();
      setDates(data.screening_dates || []);
    } catch (err) {
      console.error('Failed to fetch dates:', err);
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return 'Select Date';
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-IN', {
      weekday: 'short',
      day: 'numeric',
      month: 'short',
      year: 'numeric'
    });
  };

  const handleSelect = (date) => {
    onDateChange(date);
    setIsOpen(false);
  };

  return (
    <div className="date-selector">
      <button
        className="date-selector-button"
        onClick={() => setIsOpen(!isOpen)}
        disabled={loading}
      >
        <Calendar size={18} />
        <span>{selectedDate ? formatDate(selectedDate) : 'Latest Results'}</span>
        <ChevronDown size={18} className={isOpen ? 'rotated' : ''} />
      </button>

      {isOpen && (
        <div className="date-dropdown">
          <div
            className={`date-option ${!selectedDate ? 'active' : ''}`}
            onClick={() => handleSelect(null)}
          >
            <span>Latest Results</span>
          </div>
          {dates.map((item) => (
            <div
              key={item.date}
              className={`date-option ${selectedDate === item.date ? 'active' : ''}`}
              onClick={() => handleSelect(item.date)}
            >
              <span>{formatDate(item.date)}</span>
              <span className="date-count">{item.count} stocks</span>
            </div>
          ))}
          {dates.length === 0 && !loading && (
            <div className="date-option disabled">No screening data available</div>
          )}
        </div>
      )}
    </div>
  );
}

export default DateSelector;
