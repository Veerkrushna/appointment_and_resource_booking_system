import React from "react";

interface UserAvatarProps {
  photo?: string | null;
  name: string;
  size?: number;
  style?: React.CSSProperties;
  className?: string;
}

export default function UserAvatar({
  photo,
  name,
  size = 40,
  style,
  className,
}: UserAvatarProps) {
  if (photo) {
    return (
      <img
        src={photo}
        alt={name}
        className={className}
        style={{
          width: `${size}px`,
          height: `${size}px`,
          borderRadius: "50%",
          objectFit: "cover",
          flexShrink: 0,
          ...style,
        }}
      />
    );
  }

  const initial = (name || "U").trim().charAt(0).toUpperCase();

  return (
    <div
      className={className}
      aria-hidden="true"
      style={{
        width: `${size}px`,
        height: `${size}px`,
        borderRadius: "50%",
        backgroundColor: "#e2784d",
        color: "#ffffff",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontWeight: "bold",
        fontSize: `${Math.round(size * 0.42)}px`,
        flexShrink: 0,
        ...style,
      }}
    >
      {initial}
    </div>
  );
}
