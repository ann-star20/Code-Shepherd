interface SpinnerProps {
  size?: "sm" | "md" | "lg";
}

const SIZE = { sm: "h-3 w-3", md: "h-5 w-5", lg: "h-8 w-8" };

export function Spinner({ size = "md" }: SpinnerProps) {
  return (
    <span
      data-testid="spinner"
      className={`inline-block animate-spin rounded-full border-2 border-current border-t-transparent ${SIZE[size]}`}
      aria-label="loading"
    />
  );
}
