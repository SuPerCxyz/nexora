type NexoraIconProps = {
  size?: number;
};

export function NexoraIcon({ size = 14 }: NexoraIconProps) {
  return (
    <img
      src="/static/nexora-logo.png"
      alt=""
      height={size}
      className="nx-brand-icon"
      aria-hidden="true"
    />
  );
}
