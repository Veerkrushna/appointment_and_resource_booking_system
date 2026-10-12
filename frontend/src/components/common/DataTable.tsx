import React from "react";

export interface ColumnDef<T> {
  header: React.ReactNode;
  key: string;
  align?: "left" | "center" | "right";
  width?: string | number;
  className?: string;
  render?: (item: T, index: number) => React.ReactNode;
  accessor?: keyof T | ((item: T) => React.ReactNode);
}

interface DataTableProps<T> {
  columns: ColumnDef<T>[];
  data: T[];
  keyExtractor: (item: T, index: number) => string | number;
  loading?: boolean;
  loadingMessage?: string;
  error?: string | null;
  emptyMessage?: string;
  emptyContent?: React.ReactNode;
  wrapperClassName?: string;
  tableClassName?: string;
  style?: React.CSSProperties;
}

export default function DataTable<T>({
  columns,
  data,
  keyExtractor,
  loading = false,
  loadingMessage = "Loading data...",
  error = null,
  emptyMessage = "No records found.",
  emptyContent,
  wrapperClassName = "admin-table-wrapper",
  tableClassName = "admin-table",
  style,
}: DataTableProps<T>) {
  if (loading) {
    return <p style={{ padding: "1.5rem" }}>{loadingMessage}</p>;
  }

  if (error) {
    return <p style={{ padding: "1.5rem", color: "red" }}>{error}</p>;
  }

  return (
    <div className={wrapperClassName} style={style}>
      <table className={tableClassName}>
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                style={{
                  textAlign: column.align || "left",
                  width: column.width,
                }}
                className={column.className}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.length > 0 ? (
            data.map((item, index) => (
              <tr key={keyExtractor(item, index)}>
                {columns.map((column) => {
                  let cellContent: React.ReactNode = null;
                  if (column.render) {
                    cellContent = column.render(item, index);
                  } else if (typeof column.accessor === "function") {
                    cellContent = column.accessor(item);
                  } else if (column.accessor) {
                    cellContent = (item as any)[column.accessor];
                  } else {
                    cellContent = (item as any)[column.key];
                  }

                  return (
                    <td
                      key={column.key}
                      style={{ textAlign: column.align || "left" }}
                      className={column.className}
                    >
                      {cellContent}
                    </td>
                  );
                })}
              </tr>
            ))
          ) : (
            <tr>
              <td
                colSpan={columns.length}
                style={{
                  textAlign: "center",
                  padding: "2rem",
                  color: "#64748b",
                }}
              >
                {emptyContent || (
                  <p style={{ margin: 0, color: "var(--text-secondary)" }}>
                    {emptyMessage}
                  </p>
                )}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
