export function IconBranch() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="6" cy="6" r="2.2" fill="none" stroke="currentColor" strokeWidth="1.7" />
      <circle cx="6" cy="18" r="2.2" fill="none" stroke="currentColor" strokeWidth="1.7" />
      <circle cx="18" cy="12" r="2.2" fill="none" stroke="currentColor" strokeWidth="1.7" />
      <path d="M6 8.2v7.6M8.1 6.8c4.2.4 7.2 2.2 7.8 4.4" fill="none" stroke="currentColor" strokeWidth="1.7" />
    </svg>
  );
}

export function IconCluster() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="3.5" y="4" width="7" height="7" rx="1.2" fill="none" stroke="currentColor" strokeWidth="1.7" />
      <rect x="13.5" y="4" width="7" height="7" rx="1.2" fill="none" stroke="currentColor" strokeWidth="1.7" />
      <rect x="8.5" y="13" width="7" height="7" rx="1.2" fill="none" stroke="currentColor" strokeWidth="1.7" />
    </svg>
  );
}

export function IconRegistry() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <ellipse cx="12" cy="7" rx="7" ry="3" fill="none" stroke="currentColor" strokeWidth="1.7" />
      <path d="M5 7v10c0 1.7 3.1 3 7 3s7-1.3 7-3V7" fill="none" stroke="currentColor" strokeWidth="1.7" />
      <path d="M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3" fill="none" stroke="currentColor" strokeWidth="1.7" />
    </svg>
  );
}

export function IconUsers() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="9" cy="8" r="3" fill="none" stroke="currentColor" strokeWidth="1.7" />
      <path d="M3.8 19c.6-3.1 2.9-5 5.2-5s4.6 1.9 5.2 5" fill="none" stroke="currentColor" strokeWidth="1.7" />
      <circle cx="17" cy="9" r="2.3" fill="none" stroke="currentColor" strokeWidth="1.7" />
      <path d="M20.6 18.4c-.4-2.2-2-3.6-3.6-3.6" fill="none" stroke="currentColor" strokeWidth="1.7" />
    </svg>
  );
}

export function IconChevron() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M6.5 9.2 12 14.8l5.5-5.6" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function IconSidebarFold({ collapsed = false }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={collapsed ? "fold-in" : "fold-out"}>
      <path d="M9 6.5 14.5 12 9 17.5" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4.5 5.5v13" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

export function IconSettings() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="3" fill="none" stroke="currentColor" strokeWidth="1.7" />
      <path d="M12 3.5v2M12 18.5v2M4.6 7.4l1.4 1.4M18 20.6l1.4 1.4M3.5 12h2M18.5 12h2M4.6 16.6l1.4-1.4M18 7.4l1.4-1.4" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

export function IconIntegration() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="4" y="5" width="7" height="7" rx="1.2" fill="none" stroke="currentColor" strokeWidth="1.7" />
      <rect x="13" y="5" width="7" height="7" rx="1.2" fill="none" stroke="currentColor" strokeWidth="1.7" />
      <rect x="8.5" y="14" width="7" height="7" rx="1.2" fill="none" stroke="currentColor" strokeWidth="1.7" />
    </svg>
  );
}

export function IconSkill() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 3.5 4.5 7.2v5.3c0 4.2 3.2 7.2 7.5 7.8 4.3-.6 7.5-3.6 7.5-7.8V7.2Z" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
      <path d="M9.2 12.2 11.2 14.2 15.2 10.2" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function IconMcp() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M7 8.5h10M7 12h10M7 15.5h6" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
      <rect x="4.5" y="5" width="15" height="14" rx="2" fill="none" stroke="currentColor" strokeWidth="1.7" />
    </svg>
  );
}

export function IconAgent() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="7" y="4.5" width="10" height="8" rx="2" fill="none" stroke="currentColor" strokeWidth="1.7" />
      <path d="M9.5 12.5v2.5M14.5 12.5v2.5M6.5 19.5h11" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
      <circle cx="10" cy="8.5" r="1" fill="currentColor" />
      <circle cx="14" cy="8.5" r="1" fill="currentColor" />
    </svg>
  );
}

export function IconZadig() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 8.5h14v9H5z" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
      <path d="M8.5 8.5V6.8c0-1 1.2-1.8 3.5-1.8s3.5.8 3.5 1.8V8.5" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

export function IconPlus() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M12 7v10M7 12h10" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

export function IconList() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M7 8h10M7 12h10M7 16h10" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

export function IconTemplate() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <rect x="5" y="4.5" width="14" height="15" rx="2" fill="none" stroke="currentColor" strokeWidth="1.7" />
      <path d="M8.5 9h7M8.5 12.5h7M8.5 16h4.5" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

export function IconProject() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M5 7.5h14v11H5z" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
      <path d="M9 7.5V5.8c0-1 .9-1.8 3-1.8s3 .8 3 1.8V7.5" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
      <path d="M9 12h6" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

export function IconBell() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.4 1.8H4.6Z" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <path d="M10 19.4a2.2 2.2 0 0 0 4 0" fill="none" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

export const RESOURCE_ICONS = {
  "code-sources": IconBranch,
  clusters: IconCluster,
  registries: IconRegistry,
  "service-templates": IconTemplate,
  users: IconUsers,
};
