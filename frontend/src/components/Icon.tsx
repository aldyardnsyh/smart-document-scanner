type IconName =
  | "alert"
  | "check"
  | "chevron"
  | "copy"
  | "document"
  | "history"
  | "moon"
  | "plus"
  | "scan"
  | "search"
  | "sun"
  | "trash"
  | "upload"
  | "zoom-in"
  | "zoom-out";

interface IconProps {
  name: IconName;
  size?: number;
  className?: string;
}

export function Icon({ name, size = 18, className }: IconProps) {
  const content = (() => {
    switch (name) {
      case "alert":
        return <><path d="M12 3 2.8 20h18.4L12 3Z" /><path d="M12 9v5" /><path d="M12 17.2v.1" /></>;
      case "check":
        return <path d="m5 12 4 4L19 6" />;
      case "chevron":
        return <path d="m9 5 7 7-7 7" />;
      case "copy":
        return <><rect x="8" y="8" width="11" height="11" rx="1" /><path d="M16 8V5H5v11h3" /></>;
      case "document":
        return <><path d="M6 2h8l4 4v16H6Z" /><path d="M14 2v5h5" /><path d="M9 12h6M9 16h6" /></>;
      case "history":
        return <><path d="M4 5v5h5" /><path d="M5.5 9A8 8 0 1 1 4 14" /><path d="M12 8v5l3 2" /></>;
      case "moon":
        return <path d="M20 15.5A8 8 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5Z" />;
      case "plus":
        return <path d="M12 5v14M5 12h14" />;
      case "scan":
        return <><path d="M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5" /><rect x="7" y="7" width="10" height="10" /></>;
      case "search":
        return <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></>;
      case "sun":
        return <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>;
      case "trash":
        return <><path d="M4 7h16" /><path d="M9 7V4h6v3" /><path d="m6 7 1 14h10l1-14" /><path d="M10 11v6M14 11v6" /></>;
      case "upload":
        return <><path d="M12 16V4" /><path d="m7 9 5-5 5 5" /><path d="M4 15v5h16v-5" /></>;
      case "zoom-in":
        return <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5M10.5 7.5v6M7.5 10.5h6" /></>;
      case "zoom-out":
        return <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5M7.5 10.5h6" /></>;
    }
  })();
  return (
    <svg
      aria-hidden="true"
      className={className}
      fill="none"
      height={size}
      viewBox="0 0 24 24"
      width={size}
      stroke="currentColor"
      strokeLinecap="square"
      strokeLinejoin="miter"
      strokeWidth="1.7"
    >
      {content}
    </svg>
  );
}
