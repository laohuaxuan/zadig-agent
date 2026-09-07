import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import ProfileSettingsModal from "./components/ProfileSettingsModal.jsx";
import {
  IconAgent,
  IconBell,
  IconBranch,
  IconChevron,
  IconCluster,
  IconIntegration,
  IconList,
  IconMcp,
  IconPlus,
  IconProject,
  IconRegistry,
  IconSettings,
  IconSidebarFold,
  IconSkill,
  IconTemplate,
  IconUsers,
  IconZadig,
} from "./icons.jsx";
import { RESOURCES } from "./resources.js";
import { useAuth } from "./AuthContext.jsx";

const SIDEBAR = [
  {
    label: "系统设置",
    icon: IconSettings,
    groups: [
      {
        label: "系统集成",
        icon: IconIntegration,
        items: [
          { to: "/code-sources", label: "代码源", icon: IconBranch, perm: "can_view_integration" },
          { to: "/clusters", label: "集群管理", icon: IconCluster, perm: "can_view_integration" },
          { to: "/registries", label: "镜像仓库", icon: IconRegistry, perm: "can_view_integration" },
          { to: "/service-templates", label: "服务模板", icon: IconTemplate, perm: "can_view_integration" },
          { to: "/users", label: "Zadig 用户", icon: IconUsers, end: true, perm: "can_view_integration" },
        ],
      },
      {
        label: "审批相关",
        icon: IconBell,
        items: [
          { to: "/approval-config", label: "审批配置", icon: IconSettings, end: true, perm: "can_view_approval_config" },
        ],
      },
    ],
    items: [{ to: "/platform/users", label: "用户管理", icon: IconUsers, end: true, perm: "can_manage_users" }],
  },
  {
    label: "项目管理",
    icon: IconProject,
    items: [
      { to: "/projects/new", label: "创建项目", icon: IconPlus },
      { to: "/projects/add-service", label: "添加新服务", icon: IconPlus },
      { to: "/projects/add-workflow", label: "添加工作流", icon: IconPlus },
      { to: "/projects/add-environment", label: "添加新环境", icon: IconPlus, end: true },
      { to: "/workflows", label: "审批流", icon: IconBell, end: true },
    ],
  },
  {
    label: "技能",
    icon: IconSkill,
    groups: [
      {
        label: "Skills",
        icon: IconSkill,
        items: [
          { to: "/skills/new", label: "新建", icon: IconPlus, perm: "can_manage_skills" },
          { to: "/skills", label: "技能列表", icon: IconList, end: true },
        ],
      },
      {
        label: "MCP",
        icon: IconMcp,
        items: [
          { to: "/mcp/new", label: "新建", icon: IconPlus, perm: "can_manage_skills" },
          { to: "/mcp", label: "技能列表", icon: IconList, end: true },
        ],
      },
      {
        label: "Templates",
        icon: IconTemplate,
        items: [
          { to: "/templates/new", label: "新建 / 导入", icon: IconPlus, perm: "can_manage_templates" },
          { to: "/templates", label: "模板列表", icon: IconList, end: true },
        ],
      },
    ],
  },
  {
    label: "Agent 管理",
    icon: IconAgent,
    items: [
      { to: "/agents/new", label: "新增 Agent", icon: IconPlus, perm: "can_manage_agents" },
      { to: "/agents", label: "Agent 列表", icon: IconList, end: true },
    ],
  },
  {
    label: "Zadig 管理",
    icon: IconZadig,
    items: [
      { to: "/zadig/new", label: "新增 Zadig", icon: IconPlus, perm: "can_manage_zadig" },
      { to: "/zadig", label: "Zadig 列表", icon: IconList, end: true },
    ],
  },
];

const CRUMBS = {
  "/code-sources": ["系统设置", "系统集成", "代码源"],
  "/clusters": ["系统设置", "系统集成", "集群管理"],
  "/registries": ["系统设置", "系统集成", "镜像仓库"],
  "/service-templates": ["系统设置", "系统集成", "服务模板"],
  "/users": ["系统设置", "系统集成", "Zadig 用户"],
  "/platform/users": ["系统设置", "用户管理"],
  "/approval-config": ["系统设置", "审批相关", "审批配置"],
  "/workflows": ["项目管理", "审批流"],
  "/projects/new": ["项目管理", "创建项目"],
  "/projects/add-service": ["项目管理", "添加新服务"],
  "/projects/add-workflow": ["项目管理", "添加工作流"],
  "/projects/add-environment": ["项目管理", "添加新环境"],
  "/skills": ["技能", "Skills", "技能列表"],
  "/skills/new": ["技能", "Skills", "新建"],
  "/mcp": ["技能", "MCP", "技能列表"],
  "/mcp/new": ["技能", "MCP", "新建"],
  "/templates": ["技能", "Templates", "模板列表"],
  "/templates/new": ["技能", "Templates", "新建 / 导入"],
  "/agents": ["Agent 管理", "Agent 列表"],
  "/agents/new": ["Agent 管理", "新增 Agent"],
  "/zadig": ["Zadig 管理", "Zadig 列表"],
  "/zadig/new": ["Zadig 管理", "新增 Zadig"],
};

const GROUP_COLLAPSE_KEY = "zadig-nav-collapsed";
const SIDEBAR_COLLAPSE_KEY = "zadig-sidebar-collapsed";

function crumbsFor(pathname) {
  if (CRUMBS[pathname]) return CRUMBS[pathname];
  if (pathname.startsWith("/agents/") && pathname.endsWith("/edit")) {
    return ["Agent 管理", "编辑 Agent"];
  }
  if (pathname.startsWith("/zadig/") && pathname.endsWith("/edit")) {
    return ["Zadig 管理", "编辑 Zadig"];
  }
  if (pathname.startsWith("/skills/") && pathname !== "/skills/new") {
    return ["技能", "Skills", "技能详情"];
  }
  if (pathname.startsWith("/mcp/") && pathname !== "/mcp/new") {
    return ["技能", "MCP", "技能详情"];
  }
  if (pathname.startsWith("/templates/") && pathname !== "/templates/new") {
    return ["技能", "Templates", "模板详情"];
  }
  const resource = RESOURCES[pathname.slice(1)];
  if (resource) {
    if (pathname.slice(1) === "users") return ["系统设置", resource.title];
    return ["系统设置", "系统集成", resource.title];
  }
  return ["系统设置"];
}

function itemMatches(item, pathname) {
  if (item.end) return pathname === item.to;
  return pathname === item.to || pathname.startsWith(`${item.to}/`);
}

function collectItems(section) {
  const direct = section.items || [];
  const grouped = section.groups?.flatMap((group) => group.items) || [];
  return [...direct, ...grouped];
}

function visibleItems(items, permissions = {}) {
  return items.filter((item) => !item.perm || permissions[item.perm]);
}

function visibleSection(section, permissions = {}) {
  const direct = visibleItems(section.items || [], permissions);
  const groups = (section.groups || [])
    .map((group) => ({ ...group, items: visibleItems(group.items, permissions) }))
    .filter((group) => group.items.length > 0);
  return { ...section, items: direct.length ? direct : undefined, groups: groups.length ? groups : undefined };
}

function sectionHasNav(section, permissions = {}) {
  const normalized = visibleSection(section, permissions);
  return Boolean(normalized.items?.length || normalized.groups?.length);
}

function sectionContains(section, pathname) {
  return collectItems(section).some((item) => itemMatches(item, pathname));
}

function readGroupCollapsed() {
  try {
    const raw = JSON.parse(localStorage.getItem(GROUP_COLLAPSE_KEY) || "[]");
    return new Set(Array.isArray(raw) ? raw.filter((item) => typeof item === "string") : []);
  } catch {
    return new Set();
  }
}

function readSidebarCollapsed() {
  return localStorage.getItem(SIDEBAR_COLLAPSE_KEY) === "1";
}

function NavItems({ items, compact = false, permissions = {} }) {
  return items
    .filter((item) => !item.perm || permissions[item.perm])
    .map((item) => {
    const Icon = item.icon;
    return (
      <NavLink
        key={item.to}
        to={item.to}
        end={Boolean(item.end)}
        title={compact ? item.label : undefined}
        className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}
      >
        {Icon ? (
          <span className="nav-icon" aria-hidden="true">
            <Icon />
          </span>
        ) : null}
        <span className="nav-text">{item.label}</span>
      </NavLink>
    );
  });
}

function FoldButton({ label, open, onToggle, nested = false, icon: Icon }) {
  return (
    <button
      type="button"
      className={`nav-fold${nested ? " nested" : ""}${open ? " open" : ""}`}
      aria-expanded={open}
      onClick={onToggle}
    >
      <span className="nav-fold-leading">
        <IconChevron />
        {Icon ? (
          <span className="nav-icon" aria-hidden="true">
            <Icon />
          </span>
        ) : null}
      </span>
      <span className="nav-text">{label}</span>
    </button>
  );
}

export default function Layout() {
  const location = useLocation();
  const { user, logout, permissions, refresh } = useAuth();
  const crumbs = crumbsFor(location.pathname);
  const [groupCollapsed, setGroupCollapsed] = useState(readGroupCollapsed);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(readSidebarCollapsed);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const userMenuRef = useRef(null);
  const userMenuCloseTimer = useRef(null);

  useEffect(() => {
    setGroupCollapsed((prev) => {
      const next = new Set(prev);
      for (const section of SIDEBAR) {
        if (sectionContains(section, location.pathname)) {
          next.delete(section.label);
          for (const group of section.groups || []) {
            if (group.items.some((item) => itemMatches(item, location.pathname))) {
              next.delete(`${section.label}/${group.label}`);
            }
          }
        }
      }
      return next;
    });
  }, [location.pathname]);

  function toggleGroup(key) {
    setGroupCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      localStorage.setItem(GROUP_COLLAPSE_KEY, JSON.stringify([...next]));
      return next;
    });
  }

  function toggleSidebar() {
    setSidebarCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem(SIDEBAR_COLLAPSE_KEY, next ? "1" : "0");
      return next;
    });
  }

  function openUserMenu() {
    if (userMenuCloseTimer.current) {
      clearTimeout(userMenuCloseTimer.current);
      userMenuCloseTimer.current = null;
    }
    setUserMenuOpen(true);
  }

  function closeUserMenu() {
    if (userMenuCloseTimer.current) {
      clearTimeout(userMenuCloseTimer.current);
      userMenuCloseTimer.current = null;
    }
    setUserMenuOpen(false);
  }

  function scheduleCloseUserMenu() {
    if (userMenuCloseTimer.current) clearTimeout(userMenuCloseTimer.current);
    userMenuCloseTimer.current = setTimeout(() => {
      setUserMenuOpen(false);
      userMenuCloseTimer.current = null;
    }, 300);
  }

  useEffect(() => () => {
    if (userMenuCloseTimer.current) clearTimeout(userMenuCloseTimer.current);
  }, []);

  const flatItems = SIDEBAR.flatMap((section) => collectItems(visibleSection(section, permissions)));

  return (
    <div className={`app-shell${sidebarCollapsed ? " sidebar-collapsed" : ""}`}>
      <aside className="sidebar">
        <div className="sidebar-top">
          <div className="brand">
            <span className="brand-mark">ZA</span>
            <div className="brand-copy">
              <strong>Zadig Agent</strong>
              <p>系统设置</p>
            </div>
          </div>
          {!sidebarCollapsed ? (
            <button type="button" className="sidebar-toggle" aria-label="折叠导航栏" title="折叠导航栏" onClick={toggleSidebar}>
              <IconSidebarFold collapsed={false} />
            </button>
          ) : null}
        </div>

        {sidebarCollapsed ? (
          <div className="nav-compact">
            <NavItems items={flatItems} compact permissions={permissions} />
          </div>
        ) : (
          SIDEBAR.filter((section) => sectionHasNav(section, permissions)).map((section) => {
            const visible = visibleSection(section, permissions);
            const open = !groupCollapsed.has(section.label);
            return (
              <div className="nav-group" key={section.label}>
                <FoldButton label={section.label} icon={section.icon} open={open} onToggle={() => toggleGroup(section.label)} />
                {open ? (
                  <div className="nav-body">
                    {visible.items ? <NavItems items={visible.items} permissions={permissions} /> : null}
                    {visible.groups?.map((group) => {
                      const groupKey = `${section.label}/${group.label}`;
                      const groupOpen = !groupCollapsed.has(groupKey);
                      return (
                        <div className="nav-sub" key={group.label}>
                          <FoldButton label={group.label} icon={group.icon} open={groupOpen} nested onToggle={() => toggleGroup(groupKey)} />
                          {groupOpen ? <NavItems items={group.items} permissions={permissions} /> : null}
                        </div>
                      );
                    })}
                  </div>
                ) : null}
              </div>
            );
          })
        )}

        <div className="sidebar-footer">
          {sidebarCollapsed ? (
            <button type="button" className="sidebar-toggle expanded" aria-label="展开导航栏" title="展开导航栏" onClick={toggleSidebar}>
              <IconSidebarFold collapsed />
            </button>
          ) : null}
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <div className="topbar-left">
            <h2 className="topbar-title">{crumbs[crumbs.length - 1]}</h2>
          </div>
          <div className="top-actions">
            <button type="button" className="icon-btn" aria-label="通知">
              <IconBell />
            </button>
            <div
              ref={userMenuRef}
              className={`user-menu${userMenuOpen ? " keep-open" : ""}`}
              onMouseEnter={openUserMenu}
              onMouseLeave={scheduleCloseUserMenu}
            >
              <button
                type="button"
                className="user-btn"
                onClick={() => {
                  if (userMenuOpen) closeUserMenu();
                  else openUserMenu();
                }}
              >
                <span className="user-avatar">{(user?.display_name || user?.name || "U").slice(0, 1).toUpperCase()}</span>
                <span className="user-details">
                  <span className="user-name">{user?.display_name || user?.name || "用户"}</span>
                  <span className="user-role">{user?.role_label || user?.role || "—"}</span>
                </span>
              </button>
              <div className="user-dropdown" onMouseEnter={openUserMenu} onMouseLeave={scheduleCloseUserMenu}>
                <button
                  type="button"
                  className="dropdown-item"
                  onClick={() => {
                    closeUserMenu();
                    setProfileOpen(true);
                  }}
                >
                  个人设置
                </button>
                <button
                  type="button"
                  className="dropdown-item logout-btn"
                  onClick={() => {
                    closeUserMenu();
                    logout();
                  }}
                >
                  退出登录
                </button>
              </div>
            </div>
          </div>
        </header>
        <div className="content">
          <Outlet />
        </div>
        <ProfileSettingsModal
          open={profileOpen}
          onClose={() => setProfileOpen(false)}
          onSaved={() => refresh()}
        />
      </div>
    </div>
  );
}
