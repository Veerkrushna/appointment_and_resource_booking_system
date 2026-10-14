import React, { useEffect } from "react";

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  minWidth?: string;
  maxWidth?: string;
}

export default function Modal({
  isOpen,
  onClose,
  title,
  children,
  footer,
  minWidth = "320px",
  maxWidth = "90%",
}: ModalProps) {
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: "rgba(0, 0, 0, 0.5)",
        zIndex: 1000,
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        padding: "1rem",
        boxSizing: "border-box",
      }}
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        style={{
          background: "#ffffff",
          padding: "1.75rem",
          borderRadius: "8px",
          minWidth,
          maxWidth,
          boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.2)",
          boxSizing: "border-box",
          position: "relative",
          maxHeight: "90vh",
          overflowY: "auto",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {title && (
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "1.25rem",
              borderBottom: "1px solid #f1f5f9",
              paddingBottom: "0.75rem",
            }}
          >
            <h3 style={{ margin: 0, color: "#18312f", fontSize: "1.2rem" }}>
              {title}
            </h3>
            <button
              type="button"
              onClick={onClose}
              style={{
                background: "transparent",
                border: "none",
                fontSize: "1.25rem",
                cursor: "pointer",
                color: "#64748b",
                padding: "0.2rem 0.5rem",
                borderRadius: "4px",
              }}
              aria-label="Close dialog"
            >
              ✕
            </button>
          </div>
        )}

        <div style={{ margin: title ? "0.5rem 0 1rem" : "0 0 1rem" }}>
          {children}
        </div>

        {footer ? (
          <div
            style={{
              display: "flex",
              justifyContent: "flex-end",
              gap: "0.5rem",
              marginTop: "1.25rem",
              borderTop: "1px solid #f1f5f9",
              paddingTop: "0.75rem",
            }}
          >
            {footer}
          </div>
        ) : (
          <div
            style={{
              display: "flex",
              justifyContent: "flex-end",
              marginTop: "1rem",
            }}
          >
            <button
              type="button"
              className="admin-table-edit-btn"
              onClick={onClose}
              style={{ padding: "0.45rem 1rem" }}
            >
              Close
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
