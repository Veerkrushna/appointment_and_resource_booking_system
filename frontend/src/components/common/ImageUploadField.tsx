import React, { useState } from "react";

interface ImageUploadFieldProps {
  value?: string | null;
  onChange: (url: string | null) => void;
  onError?: (error: string | null) => void;
  label?: string;
  maxSizeMB?: number;
  accept?: string;
  disabled?: boolean;
}

export default function ImageUploadField({
  value,
  onChange,
  onError,
  label = "Photo (.jpg, .jpeg)",
  maxSizeMB = 1.5,
  accept = ".jpg,.jpeg",
  disabled = false,
}: ImageUploadFieldProps) {
  const [isUploading, setIsUploading] = useState(false);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const lowerName = file.name.toLowerCase();
    const allowedExtensions = accept.split(",").map((s) => s.trim().toLowerCase());
    const matchesExtension = allowedExtensions.some((ext) =>
      lowerName.endsWith(ext),
    );

    if (!matchesExtension) {
      const err = `Only ${accept} files are allowed.`;
      if (onError) onError(err);
      return;
    }

    if (file.size > maxSizeMB * 1024 * 1024) {
      const err = `Photo size must not exceed ${maxSizeMB} MB.`;
      if (onError) onError(err);
      return;
    }

    if (onError) onError(null);
    setIsUploading(true);

    const uploadData = new FormData();
    uploadData.append("file", file);

    try {
      const res = await fetch("/api/upload/image", {
        method: "POST",
        body: uploadData,
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => null);
        throw new Error(errorData?.detail || "Photo upload failed");
      }

      const data = await res.json();
      onChange(data.url);
    } catch (err: any) {
      if (onError) onError(err.message || "Failed to upload photo");
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div>
      {label && <label>{label}</label>}
      <div style={{ display: "flex", gap: "1rem", alignItems: "center" }}>
        <input
          type="file"
          accept={accept}
          onChange={handleFileChange}
          disabled={disabled || isUploading}
          style={{
            flex: 1,
            padding: "0.5rem",
            border: "1px solid #ccc",
            borderRadius: "4px",
          }}
        />
        {isUploading && (
          <span style={{ fontSize: "0.85rem", color: "#e2784d" }}>
            Uploading...
          </span>
        )}
        {value && (
          <div style={{ position: "relative" }}>
            <img
              src={value}
              alt="Uploaded Preview"
              style={{
                width: "40px",
                height: "40px",
                borderRadius: "50%",
                objectFit: "cover",
                flexShrink: 0,
              }}
            />
          </div>
        )}
      </div>
    </div>
  );
}
