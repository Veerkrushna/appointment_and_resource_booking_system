import { useState, useEffect, useRef } from "react";

interface AntTimeRangePickerProps {
  value?: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

const HOURS = Array.from({ length: 12 }, (_, i) =>
  String(i + 1).padStart(2, "0"),
);
const MINUTES = Array.from({ length: 12 }, (_, i) =>
  String(i * 5).padStart(2, "0"),
);
const PERIODS = ["AM", "PM"];

export default function AntTimeRangePicker({
  value = "",
  onChange,
  placeholder = "HH:MM am/pm to HH:MM am/pm",
}: AntTimeRangePickerProps) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Parse initial value if present
  const parseTimeRange = (str: string) => {
    const match = str.match(
      /^\s*(\d{1,2}):(\d{2})\s*(am|pm|AM|PM)\s+to\s+(\d{1,2}):(\d{2})\s*(am|pm|AM|PM)\s*$/i,
    );
    if (match) {
      return {
        sh: match[1].padStart(2, "0"),
        sm: match[2].padStart(2, "0"),
        sp: match[3].toUpperCase(),
        eh: match[4].padStart(2, "0"),
        em: match[5].padStart(2, "0"),
        ep: match[6].toUpperCase(),
      };
    }
    return {
      sh: "09",
      sm: "00",
      sp: "AM",
      eh: "05",
      em: "00",
      ep: "PM",
    };
  };

  const parsed = parseTimeRange(value);
  const [startHour, setStartHour] = useState(parsed.sh);
  const [startMinute, setStartMinute] = useState(parsed.sm);
  const [startPeriod, setStartPeriod] = useState(parsed.sp);

  const [endHour, setEndHour] = useState(parsed.eh);
  const [endMinute, setEndMinute] = useState(parsed.em);
  const [endPeriod, setEndPeriod] = useState(parsed.ep);

  useEffect(() => {
    if (value) {
      const p = parseTimeRange(value);
      setStartHour(p.sh);
      setStartMinute(p.sm);
      setStartPeriod(p.sp);
      setEndHour(p.eh);
      setEndMinute(p.em);
      setEndPeriod(p.ep);
    }
  }, [value]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  const updateRange = (
    sh: string,
    sm: string,
    sp: string,
    eh: string,
    em: string,
    ep: string,
  ) => {
    const formatted = `${sh}:${sm} ${sp.toLowerCase()} to ${eh}:${em} ${ep.toLowerCase()}`;
    onChange(formatted);
  };

  const handleStartHour = (h: string) => {
    setStartHour(h);
    updateRange(h, startMinute, startPeriod, endHour, endMinute, endPeriod);
  };

  const handleStartMinute = (m: string) => {
    setStartMinute(m);
    updateRange(startHour, m, startPeriod, endHour, endMinute, endPeriod);
  };

  const handleStartPeriod = (p: string) => {
    setStartPeriod(p);
    updateRange(startHour, startMinute, p, endHour, endMinute, endPeriod);
  };

  const handleEndHour = (h: string) => {
    setEndHour(h);
    updateRange(startHour, startMinute, startPeriod, h, endMinute, endPeriod);
  };

  const handleEndMinute = (m: string) => {
    setEndMinute(m);
    updateRange(startHour, startMinute, startPeriod, endHour, m, endPeriod);
  };

  const handleEndPeriod = (p: string) => {
    setEndPeriod(p);
    updateRange(startHour, startMinute, startPeriod, endHour, endMinute, p);
  };

  const handleApply = () => {
    updateRange(
      startHour,
      startMinute,
      startPeriod,
      endHour,
      endMinute,
      endPeriod,
    );
    setIsOpen(false);
  };

  const handleClear = () => {
    onChange("");
    setIsOpen(false);
  };

  return (
    <div className="ant-time-picker-wrapper" ref={containerRef}>
      <div
        className="ant-time-picker-trigger"
        onClick={() => setIsOpen(!isOpen)}
        tabIndex={0}
      >
        <span className="ant-time-picker-value">
          {value || (
            <span className="ant-time-picker-placeholder">{placeholder}</span>
          )}
        </span>
        <span className="ant-time-picker-icon">🕒</span>
      </div>

      {isOpen && (
        <div className="ant-picker-dropdown">
          <div className="ant-picker-panel-container">
            <div className="ant-time-picker-panels-row">
              {/* Start Time Column */}
              <div className="ant-time-picker-section">
                <div className="ant-time-picker-section-title">Start Time</div>
                <div className="ant-picker-time-panel">
                  <div className="ant-picker-time-panel-inner">
                    {/* Hour Column */}
                    <ul className="ant-picker-time-panel-column">
                      {HOURS.map((h) => (
                        <li
                          key={h}
                          className={`ant-picker-time-panel-cell ${
                            startHour === h
                              ? "ant-picker-time-panel-cell-selected"
                              : ""
                          }`}
                          onClick={() => handleStartHour(h)}
                        >
                          <div className="ant-picker-time-panel-cell-inner ant-time-picker-panel-inner-cell">
                            {h}
                          </div>
                        </li>
                      ))}
                    </ul>

                    {/* Minute Column */}
                    <ul className="ant-picker-time-panel-column">
                      {MINUTES.map((m) => (
                        <li
                          key={m}
                          className={`ant-picker-time-panel-cell ${
                            startMinute === m
                              ? "ant-picker-time-panel-cell-selected"
                              : ""
                          }`}
                          onClick={() => handleStartMinute(m)}
                        >
                          <div className="ant-picker-time-panel-cell-inner ant-time-picker-panel-inner-cell">
                            {m}
                          </div>
                        </li>
                      ))}
                    </ul>

                    {/* AM / PM Column */}
                    <ul className="ant-picker-time-panel-column ant-picker-time-panel-column-ampm">
                      {PERIODS.map((p) => (
                        <li
                          key={p}
                          className={`ant-picker-time-panel-cell ${
                            startPeriod === p
                              ? "ant-picker-time-panel-cell-selected"
                              : ""
                          }`}
                          onClick={() => handleStartPeriod(p)}
                        >
                          <div className="ant-picker-time-panel-cell-inner ant-time-picker-panel-inner-cell">
                            {p}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>

              <div className="ant-time-picker-separator">to</div>

              {/* End Time Column */}
              <div className="ant-time-picker-section">
                <div className="ant-time-picker-section-title">End Time</div>
                <div className="ant-picker-time-panel">
                  <div className="ant-picker-time-panel-inner">
                    {/* Hour Column */}
                    <ul className="ant-picker-time-panel-column">
                      {HOURS.map((h) => (
                        <li
                          key={h}
                          className={`ant-picker-time-panel-cell ${
                            endHour === h
                              ? "ant-picker-time-panel-cell-selected"
                              : ""
                          }`}
                          onClick={() => handleEndHour(h)}
                        >
                          <div className="ant-picker-time-panel-cell-inner ant-time-picker-panel-inner-cell">
                            {h}
                          </div>
                        </li>
                      ))}
                    </ul>

                    {/* Minute Column */}
                    <ul className="ant-picker-time-panel-column">
                      {MINUTES.map((m) => (
                        <li
                          key={m}
                          className={`ant-picker-time-panel-cell ${
                            endMinute === m
                              ? "ant-picker-time-panel-cell-selected"
                              : ""
                          }`}
                          onClick={() => handleEndMinute(m)}
                        >
                          <div className="ant-picker-time-panel-cell-inner ant-time-picker-panel-inner-cell">
                            {m}
                          </div>
                        </li>
                      ))}
                    </ul>

                    {/* AM / PM Column */}
                    <ul className="ant-picker-time-panel-column ant-picker-time-panel-column-ampm">
                      {PERIODS.map((p) => (
                        <li
                          key={p}
                          className={`ant-picker-time-panel-cell ${
                            endPeriod === p
                              ? "ant-picker-time-panel-cell-selected"
                              : ""
                          }`}
                          onClick={() => handleEndPeriod(p)}
                        >
                          <div className="ant-picker-time-panel-cell-inner ant-time-picker-panel-inner-cell">
                            {p}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            </div>

            {/* Footer */}
            <div className="ant-picker-footer">
              <button
                type="button"
                className="ant-picker-btn-clear"
                onClick={handleClear}
              >
                Clear
              </button>
              <button
                type="button"
                className="ant-picker-btn-ok"
                onClick={handleApply}
              >
                OK
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
