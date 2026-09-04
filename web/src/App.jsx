import { Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./AuthContext.jsx";
import { RequirePerm } from "./RequirePerm.jsx";
import Layout from "./Layout.jsx";
import Login from "./pages/Login.jsx";
import ResourcePage from "./pages/ResourcePage.jsx";
import ProjectCreate from "./pages/ProjectCreate.jsx";
import ServiceAdd from "./pages/ServiceAdd.jsx";
import WorkflowAdd from "./pages/WorkflowAdd.jsx";
import SkillCreate from "./pages/SkillCreate.jsx";
import SkillDetail from "./pages/SkillDetail.jsx";
import SkillList from "./pages/SkillList.jsx";
import TemplateCreate from "./pages/TemplateCreate.jsx";
import TemplateDetail from "./pages/TemplateDetail.jsx";
import TemplateList from "./pages/TemplateList.jsx";
import AgentForm from "./pages/AgentForm.jsx";
import AgentList from "./pages/AgentList.jsx";
import ZadigForm from "./pages/ZadigForm.jsx";
import ZadigList from "./pages/ZadigList.jsx";
import PlatformUsers from "./pages/PlatformUsers.jsx";
import WorkflowPanel from "./pages/WorkflowPanel.jsx";
import ApprovalConfig from "./pages/ApprovalConfig.jsx";

function ProtectedLayout() {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <section>
        <div className="skeleton-list" aria-busy="true">
          <div className="skeleton" />
        </div>
      </section>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  return <Layout />;
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<ProtectedLayout />}>
          <Route
            path="/"
            element={
              <RequirePerm perm="can_view_integration" fallback="/workflows">
                <Navigate to="/code-sources" replace />
              </RequirePerm>
            }
          />
          <Route path="/workflows" element={<WorkflowPanel />} />
          <Route
            path="/approval-config"
            element={
              <RequirePerm perm="can_view_approval_config">
                <ApprovalConfig />
              </RequirePerm>
            }
          />
          <Route
            path="/platform/users"
            element={
              <RequirePerm perm="can_manage_users">
                <PlatformUsers />
              </RequirePerm>
            }
          />
          <Route
            path="/skills/new"
            element={
              <RequirePerm perm="can_manage_skills">
                <SkillCreate kind="skill" />
              </RequirePerm>
            }
          />
          <Route path="/skills/:skillName" element={<SkillDetail kind="skill" />} />
          <Route path="/skills" element={<SkillList kind="skill" />} />
          <Route
            path="/mcp/new"
            element={
              <RequirePerm perm="can_manage_skills">
                <SkillCreate kind="mcp" />
              </RequirePerm>
            }
          />
          <Route path="/mcp/:skillName" element={<SkillDetail kind="mcp" />} />
          <Route path="/mcp" element={<SkillList kind="mcp" />} />
          <Route
            path="/templates/new"
            element={
              <RequirePerm perm="can_manage_templates">
                <TemplateCreate />
              </RequirePerm>
            }
          />
          <Route path="/templates/:templateName" element={<TemplateDetail />} />
          <Route path="/templates" element={<TemplateList />} />
          <Route path="/projects/new" element={<ProjectCreate />} />
          <Route path="/projects/add-service" element={<ServiceAdd />} />
          <Route path="/projects/add-workflow" element={<WorkflowAdd />} />
          <Route
            path="/agents/new"
            element={
              <RequirePerm perm="can_manage_agents">
                <AgentForm />
              </RequirePerm>
            }
          />
          <Route
            path="/agents/:agentId/edit"
            element={
              <RequirePerm perm="can_manage_agents">
                <AgentForm />
              </RequirePerm>
            }
          />
          <Route path="/agents" element={<AgentList />} />
          <Route
            path="/zadig/new"
            element={
              <RequirePerm perm="can_manage_zadig">
                <ZadigForm />
              </RequirePerm>
            }
          />
          <Route
            path="/zadig/:instanceId/edit"
            element={
              <RequirePerm perm="can_manage_zadig">
                <ZadigForm />
              </RequirePerm>
            }
          />
          <Route path="/zadig" element={<ZadigList />} />
          <Route
            path="/:resourceKey"
            element={
              <RequirePerm perm="can_view_integration" fallback="/workflows">
                <ResourcePage />
              </RequirePerm>
            }
          />
        </Route>
      </Routes>
    </AuthProvider>
  );
}
