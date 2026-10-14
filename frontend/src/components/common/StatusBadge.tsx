import React from "react";

interface StatusBadgeProps {
  status: string;
  label?: string;
  style?: React.CSSProperties;
  className?: string;
}

export default function StatusBadge({
  status,
  label,
  style,
  className,
}: StatusBadgeProps) {
  const normalized = (status || "").toLowerCase().trim();

  let bg = "#f1f5f9";
  let color = "#475569";
  let border = "1px solid transparent";

  if (["active", "available", "confirmed", "completed"].includes(normalized)) {
    bg = "#dcfce7";
    color = "#16a34a";
    border = "1px solid #bbf7d0";
  } else if (["cancelled", "inactive"].includes(normalized)) {
    bg = "#fee2e2";
    color = "#dc2626";
    border = "1px solid #fecaca";
  } else if (["on_leave", "limited", "in_progress"].includes(normalized)) {
    bg = "#fef3c7";
    color = "#d97706";
    border = "1px solid #fde68a";
  }

  const displayText =
    label ||
    status
      .replace(/_/g, " ")
      .replace(/\b\w/g, (char) => char.toUpperCase());

  return (
    <span
      className={className}
      style={{
        display: "inline-block",
        padding: "0.2rem 0.55rem",
        borderRadius: "4px",
        fontSize: "0.78rem",
        fontWeight: 600,
        backgroundColor: bg,
        color: color,
        border: border,
        textTransform: "capitalize",
        ...style,
      }}
    >
      {displayText}
    </span>
  );
}
