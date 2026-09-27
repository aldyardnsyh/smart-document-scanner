import { Icon } from "./Icon";

interface EmptyStateProps {
  title: string;
  description: string;
  action?: React.ReactNode;
  // "danger" marks a run that genuinely failed, so it cannot be mistaken for an empty
  // or not-yet-loaded state.
  tone?: "neutral" | "danger";
  icon?: "document" | "alert";
}

export function EmptyState({ title, description, action, tone = "neutral", icon = "document" }: EmptyStateProps) {
  return (
    <div className={`empty-state empty-state--${tone}`}>
      <span className="empty-state__icon"><Icon name={icon} size={26} /></span>
      <h2>{title}</h2>
      <p>{description}</p>
      {action}
    </div>
  );
}
