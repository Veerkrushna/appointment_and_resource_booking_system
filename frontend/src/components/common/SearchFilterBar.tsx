import React from "react";

interface SearchFilterBarProps {
  searchValue: string;
  onSearchChange: (value: string) => void;
  searchPlaceholder?: string;
  children?: React.ReactNode;
  onClear: () => void;
  resultCount?: {
    current: number;
    total: number;
    entityName?: string;
  };
}

export default function SearchFilterBar({
  searchValue,
  onSearchChange,
  searchPlaceholder = "Search...",
  children,
  onClear,
  resultCount,
}: SearchFilterBarProps) {
  return (
    <>
      <div className="admin-services-filters">
        <label className="admin-services-filter-field admin-services-filter-field--search">
          <span className="admin-services-filter-label">Search</span>
          <input
            type="search"
            placeholder={searchPlaceholder}
            value={searchValue}
            onChange={(event) => onSearchChange(event.target.value)}
            aria-label={searchPlaceholder}
          />
        </label>

        {children}

        <button
          type="button"
          className="admin-secondary-button admin-services-clear-filters"
          onClick={onClear}
        >
          Clear Filters
        </button>
      </div>

      {resultCount && (
        <p className="admin-services-result-count">
          Showing {resultCount.current} of {resultCount.total}{" "}
          {resultCount.entityName || "items"}
        </p>
      )}
    </>
  );
}
