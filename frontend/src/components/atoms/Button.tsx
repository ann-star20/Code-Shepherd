import { Spinner } from "./Spinner";

interface ButtonProps {
  variant?: "primary" | "danger" | "ghost";
  onClick?: () => void;
  disabled?: boolean;
  loading?: boolean;
  children: React.ReactNode;
}

const VARIANT_CLASS = {
  primary: "bg-blue-600 text-white hover:bg-blue-700",
  danger:  "bg-red-600  text-white hover:bg-red-700",
  ghost:   "bg-transparent text-gray-700 hover:bg-gray-100",
};

export function Button({ variant = "primary", onClick, disabled, loading, children }: ButtonProps) {
  return (
    <button
      type="button"
      className={`inline-flex items-center gap-2 rounded px-3 py-1.5 text-sm font-medium transition-colors
        ${VARIANT_CLASS[variant]}
        ${disabled || loading ? "cursor-not-allowed opacity-50" : ""}`}
      disabled={disabled || loading}
      onClick={onClick}
    >
      {loading && <Spinner size="sm" />}
      {children}
    </button>
  );
}
