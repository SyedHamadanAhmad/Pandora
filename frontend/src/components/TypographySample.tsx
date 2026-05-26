import { sampleLorem } from "../utils/lorem";
import "./TypographySample.css";

interface TypographySampleProps {
  tokenKey: string;
  value: string;
  style?: React.CSSProperties;
}

export function TypographySample({ tokenKey, value, style }: TypographySampleProps) {
  const sample = sampleLorem(tokenKey);

  return (
    <div className="typography-sample">
      <div className="typography-sample__meta">
        <span className="typography-sample__key">{tokenKey}</span>
        <span className="typography-sample__value">{value}</span>
      </div>
      <p className="typography-sample__line" style={style}>
        {sample}
      </p>
    </div>
  );
}
