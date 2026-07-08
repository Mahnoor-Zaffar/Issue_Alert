import { useEffect } from "react";

export default function Toast({ message, type = "info", onClose }) {
  useEffect(() => {
    if (!message) return;
    const t = setTimeout(onClose, 4000);
    return () => clearTimeout(t);
  }, [message, onClose]);

  if (!message) return null;

  return (
    <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[100] animate-[fadeIn_0.2s_ease-out]">
      <div
        className={`px-4 py-[10px] rounded-lg text-[13px] font-medium shadow-lg border backdrop-blur-sm
          ${type === "success" ? "bg-success/15 text-success border-success/25" : ""}
          ${type === "error" ? "bg-error/15 text-error border-error/25" : ""}
          ${type === "info" ? "bg-primary/15 text-primary-hover border-primary/25" : ""}
        `}
      >
        {message}
      </div>
    </div>
  );
}
