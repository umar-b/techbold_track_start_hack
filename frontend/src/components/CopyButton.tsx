import { Check, Copy } from "lucide-react";
import { useClipboard } from "../hooks/useClipboard";

type Props = {
  text: string;
  label?: string;
  size?: number;
};

/** Small icon button that copies `text` and flips to a check for ~1.5s. */
export function CopyButton({ text, label = "Copy command", size = 12 }: Props) {
  const { copied, copy } = useClipboard();
  return (
    <button
      type="button"
      className="icon-btn"
      aria-label={copied ? "Copied" : label}
      title={copied ? "Copied" : label}
      onClick={(e) => {
        e.stopPropagation();
        void copy(text);
      }}
    >
      {copied ? <Check size={size} style={{ color: "var(--safe)" }} /> : <Copy size={size} />}
    </button>
  );
}
