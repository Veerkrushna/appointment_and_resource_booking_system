import React from "react";
import { formatMonth, getCalendarDays, dateKey } from "../../utils/dateUtils";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

interface CalendarGridProps {
  currentDate: Date;
  onDateChange: (date: Date) => void;
  view?: "month" | "week";
  onViewChange?: (view: "month" | "week") => void;
  selectedDate?: Date | null;
  onDateSelect?: (date: Date) => void;
  renderDayContent?: (date: Date, isCurrentMonth: boolean) => React.ReactNode;
  headerControls?: React.ReactNode;
}

export default function CalendarGrid({
  currentDate,
  onDateChange,
  view = "month",
  onViewChange,
  selectedDate,
  onDateSelect,
  renderDayContent,
  headerControls,
}: CalendarGridProps) {
  const calendarDays = getCalendarDays(currentDate, view);
  const currentMonthIndex = currentDate.getMonth();

  const handlePrev = () => {
    const next = new Date(currentDate);
    if (view === "week") {
      next.setDate(next.getDate() - 7);
    } else {
      next.setMonth(next.getMonth() - 1);
    }
    onDateChange(next);
  };

  const handleNext = () => {
    const next = new Date(currentDate);
    if (view === "week") {
      next.setDate(next.getDate() + 7);
    } else {
      next.setMonth(next.getMonth() + 1);
    }
    onDateChange(next);
  };

  const handleToday = () => {
    onDateChange(new Date());
  };

  return (
    <div className="calendar-widget-container">
      <div
        className="calendar-header"
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "1rem",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <button
            type="button"
            className="calendar-nav-btn"
            onClick={handlePrev}
            aria-label="Previous period"
            style={{
              padding: "0.4rem 0.75rem",
              borderRadius: "4px",
              border: "1px solid #cbd5e1",
              background: "#fff",
              cursor: "pointer",
            }}
          >
            ‹
          </button>
          <strong style={{ fontSize: "1.1rem", minWidth: "140px", textAlign: "center" }}>
            {formatMonth(currentDate)}
          </strong>
          <button
            type="button"
            className="calendar-nav-btn"
            onClick={handleNext}
            aria-label="Next period"
            style={{
              padding: "0.4rem 0.75rem",
              borderRadius: "4px",
              border: "1px solid #cbd5e1",
              background: "#fff",
              cursor: "pointer",
            }}
          >
            ›
          </button>
          <button
            type="button"
            onClick={handleToday}
            style={{
              padding: "0.4rem 0.75rem",
              borderRadius: "4px",
              border: "1px solid #cbd5e1",
              background: "#fff",
              cursor: "pointer",
              fontSize: "0.85rem",
              marginLeft: "0.25rem",
            }}
          >
            Today
          </button>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          {onViewChange && (
            <div style={{ display: "inline-flex", borderRadius: "4px", overflow: "hidden", border: "1px solid #cbd5e1" }}>
              <button
                type="button"
                onClick={() => onViewChange("month")}
                style={{
                  padding: "0.35rem 0.75rem",
                  border: "none",
                  backgroundColor: view === "month" ? "#e2784d" : "#fff",
                  color: view === "month" ? "#fff" : "#1e293b",
                  cursor: "pointer",
                  fontSize: "0.85rem",
                }}
              >
                Month
              </button>
              <button
                type="button"
                onClick={() => onViewChange("week")}
                style={{
                  padding: "0.35rem 0.75rem",
                  border: "none",
                  backgroundColor: view === "week" ? "#e2784d" : "#fff",
                  color: view === "week" ? "#fff" : "#1e293b",
                  cursor: "pointer",
                  fontSize: "0.85rem",
                }}
              >
                Week
              </button>
            </div>
          )}
          {headerControls}
        </div>
      </div>

      <div
        className="calendar-grid-header"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(7, 1fr)",
          gap: "2px",
          textAlign: "center",
          fontWeight: 600,
          color: "#64748b",
          fontSize: "0.8rem",
          marginBottom: "0.5rem",
        }}
      >
        {WEEKDAYS.map((day) => (
          <div key={day} style={{ padding: "0.4rem" }}>
            {day}
          </div>
        ))}
      </div>

      <div
        className="calendar-grid-body"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(7, 1fr)",
          gap: "4px",
        }}
      >
        {calendarDays.map((day) => {
          const isCurrentMonth = day.getMonth() === currentMonthIndex;
          const isSelected =
            selectedDate && dateKey(day) === dateKey(selectedDate);
          const isTodayDate = dateKey(day) === dateKey(new Date());

          return (
            <div
              key={day.toISOString()}
              onClick={() => onDateSelect && onDateSelect(day)}
              style={{
                minHeight: view === "month" ? "65px" : "100px",
                padding: "0.4rem",
                borderRadius: "6px",
                border: isSelected
                  ? "2px solid #e2784d"
                  : isTodayDate
                    ? "1px solid #fdba74"
                    : "1px solid #f1f5f9",
                backgroundColor: isSelected
                  ? "#fff8f4"
                  : isCurrentMonth
                    ? "#ffffff"
                    : "#f8fafc",
                cursor: onDateSelect ? "pointer" : "default",
                opacity: isCurrentMonth ? 1 : 0.45,
                transition: "all 0.15s ease",
                display: "flex",
                flexDirection: "column",
              }}
            >
              <div
                style={{
                  fontSize: "0.8rem",
                  fontWeight: isTodayDate || isSelected ? 700 : 500,
                  color: isSelected
                    ? "#e2784d"
                    : isTodayDate
                      ? "#cf6740"
                      : "#1e293b",
                  marginBottom: "0.2rem",
                }}
              >
                {day.getDate()}
              </div>
              <div style={{ flex: 1 }}>
                {renderDayContent && renderDayContent(day, isCurrentMonth)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
