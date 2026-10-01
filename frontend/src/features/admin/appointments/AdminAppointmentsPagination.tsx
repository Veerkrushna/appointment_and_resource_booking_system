import React from "react";
import { type AdminAppointmentListResponse } from "../../../lib/adminAppointments";

type Props = {
  pagination: AdminAppointmentListResponse;
  page: number;
  setPage: React.Dispatch<React.SetStateAction<number>>;
};

export default function AdminAppointmentsPagination({
  pagination,
  page,
  setPage,
}: Props) {
  if (pagination.total_pages <= 1) {
    return null;
  }

  return (
    <div className="admin-appointments-pagination">
      <button
        type="button"
        disabled={page === 1}
        onClick={() => setPage((currentPage) => currentPage - 1)}
      >
        Previous
      </button>

      <span>
        Page {pagination.page} of {pagination.total_pages}
      </span>

      <button
        type="button"
        disabled={page >= pagination.total_pages}
        onClick={() => setPage((currentPage) => currentPage + 1)}
      >
        Next
      </button>
    </div>
  );
}
