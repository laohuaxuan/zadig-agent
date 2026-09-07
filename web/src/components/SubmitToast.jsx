import { useEffect } from "react";

export default function SubmitToast({ message, variant = "success", onClose, duration = 5000 }) {
  useEffect(() => {
    if (!message || !onClose) return undefined;
    const timer = window.setTimeout(onClose, duration);
    return () => window.clearTimeout(timer);
  }, [message, onClose, duration]);

  if (!message) return null;

  return (
    <div className={`submit-toast submit-toast-${variant}`} role={variant === "error" ? "alert" : "status"}>
      {message}
    </div>
  );
}
