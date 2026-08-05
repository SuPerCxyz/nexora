import {
  App as AntApp,
  Button,
  ConfigProvider,
  Drawer,
  Layout,
  Menu,
  Result,
  Typography,
} from "antd";
import {
  AppstoreOutlined,
  CloudServerOutlined,
  DatabaseOutlined,
  DesktopOutlined,
  DeploymentUnitOutlined,
  FileImageOutlined,
  MenuOutlined,
  SettingOutlined,
  SafetyCertificateOutlined,
  UnorderedListOutlined,
} from "@ant-design/icons";
import { useEffect, useMemo, useState } from "react";

import type { InternalSession } from "../api/contracts";
import { loadSession } from "../api/session";
import { HostsPage } from "./HostsPage";
import { HostKeyConfirmationPage } from "./HostKeyConfirmationPage";
import { HostOnboardingPage } from "./HostOnboardingPage";
import { HostDetailPage } from "./HostDetailPage";
import { OverviewPage } from "./OverviewPage";
import { PageError, PageLoading } from "./PageState";
import { PreviewPage } from "./PreviewPage";
import { StoragePage } from "./StoragePage";
import { VmsPage } from "./VmsPage";
import { VmDetailPage } from "./VmDetailPage";
import { VmConfigurationPage } from "./VmConfigurationPage";
import { VmCreatePage } from "./VmCreatePage";
import { VmBlankCreatePage } from "./VmBlankCreatePage";
import { VmMediaCreatePage } from "./VmMediaCreatePage";
import { TaskDetailPage, TasksPage } from "./TasksPage";
import { MediaPage } from "./MediaPage";
import { MediaCopyPage } from "./MediaCopyPage";
import { NetworkPage } from "./NetworkPage";
import { AuditPage } from "./AuditPage";
import { AccountPage } from "./AccountPage";
import { AuthPage } from "./AuthPage";
import { configureTimeZone } from "./dateTime";
import { nexoraTheme } from "./theme";
import "./styles.css";

const corePaths = new Set(["/", "/hosts", "/vms", "/storage", "/media", "/networks", "/tasks", "/audit", "/settings/account"]);
const navigation = [
  { key: "/", icon: <AppstoreOutlined />, label: "总览" },
  { key: "/hosts", icon: <CloudServerOutlined />, label: "节点" },
  { key: "/vms", icon: <DesktopOutlined />, label: "虚拟机" },
  { key: "/storage", icon: <DatabaseOutlined />, label: "存储" },
  { key: "/media", icon: <FileImageOutlined />, label: "镜像" },
  { key: "/networks", icon: <DeploymentUnitOutlined />, label: "网络" },
  { key: "/tasks", icon: <UnorderedListOutlined />, label: "任务" },
  { key: "/audit", icon: <SafetyCertificateOutlined />, label: "审计" },
  { key: "/settings/account", icon: <SettingOutlined />, label: "设置" },
];

type AppProps = { nonce: string };

export function App({ nonce }: AppProps) {
  const authMode = document.querySelector<HTMLMetaElement>('meta[name="nexora-auth-mode"]')?.content;
  const authError = document.querySelector<HTMLMetaElement>('meta[name="nexora-auth-error"]')?.content ?? null;
  const authCsrf = document.querySelector<HTMLMetaElement>('meta[name="nexora-auth-csrf"]')?.content ?? "";
  const [session, setSession] = useState<InternalSession | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [path, setPath] = useState(window.location.pathname);

  useEffect(() => {
    if (authMode) return;
    loadSession().then((value) => {
      configureTimeZone(value.administrator.timezone);
      setSession(value);
    }).catch(setError);
  }, [authMode]);
  useEffect(() => {
    if (!session) return;
    document.documentElement.lang = session.administrator.language;
  }, [session]);
  useEffect(() => {
    const updatePath = () => setPath(window.location.pathname);
    window.addEventListener("popstate", updatePath);
    return () => window.removeEventListener("popstate", updatePath);
  }, []);

  const selectedPath = path.startsWith("/tasks/") ? "/tasks" : corePaths.has(path) ? path : "";
  const menu = useMemo(
    () => (
      <Menu
        mode="horizontal"
        selectedKeys={[selectedPath]}
        items={navigation}
        onClick={({ key }) => navigate(key, setPath, setDrawerOpen)}
      />
    ),
    [selectedPath],
  );

  if (authMode) return <ConfigProvider theme={nexoraTheme} csp={{ nonce }}><AntApp><AuthPage mode={authMode} error={authError} csrf={authCsrf} /></AntApp></ConfigProvider>;

  return (
    <ConfigProvider theme={nexoraTheme} csp={{ nonce }}>
      <AntApp>
        <Layout className="nx-app-shell">
          <header className="nx-topbar">
            <button className="nx-brand-button" onClick={() => navigate("/", setPath, setDrawerOpen)}>
              <Typography.Title level={3} className="nx-brand">Nexora</Typography.Title>
            </button>
            <nav className="nx-desktop-nav" aria-label="主导航">{menu}</nav>
            <Button className="nx-mobile-menu" type="text" icon={<MenuOutlined />} aria-label="打开主导航" onClick={() => setDrawerOpen(true)} />
            <a className="nx-account" href="/settings/account">{session?.administrator.username ?? "管理员"}</a>
          </header>
          <Drawer title="Nexora" placement="left" open={drawerOpen} onClose={() => setDrawerOpen(false)}>
            <Menu mode="inline" selectedKeys={[selectedPath]} items={navigation} onClick={({ key }) => navigate(key, setPath, setDrawerOpen)} />
          </Drawer>
          <Layout.Content className="nx-content">
            {error ? <PageError error={error} /> : session ? <CurrentPage path={path} /> : <PageLoading />}
          </Layout.Content>
        </Layout>
      </AntApp>
    </ConfigProvider>
  );
}

function CurrentPage({ path }: { path: string }) {
  if (path === "/") return <OverviewPage />;
  if (path === "/hosts") return <HostsPage />;
  if (path === "/hosts/new") return <HostOnboardingPage />;
  if (path === "/vms") return <VmsPage />;
  if (path === "/storage") return <StoragePage />;
  if (path === "/media") return <MediaPage />;
  if (path === "/networks") return <NetworkPage />;
  if (path === "/audit") return <AuditPage />;
  if (path === "/settings/account") return <AccountPage />;
  if (path === "/tasks") return <TasksPage />;
  if (path === "/vms/create") return <VmCreatePage />;
  if (path === "/vms/create/blank-disk") return <VmBlankCreatePage />;
  if (path === "/vms/create/platform-image") return <VmMediaCreatePage />;
  const mediaCopyMatch = path.match(/^\/media\/([^/]+)\/copy$/);
  if (mediaCopyMatch) return <MediaCopyPage mediaId={mediaCopyMatch[1]} />;
  const vmMatch = path.match(/^\/hosts\/([^/]+)\/vms\/([^/]+)$/);
  const vmConfigurationMatch = path.match(/^\/(?:manage\/)?hosts\/([^/]+)\/vms\/([^/]+)\/config$/)
    ?? path.match(/^\/manage\/hosts\/([^/]+)\/vms\/([^/]+)$/);
  if (vmConfigurationMatch) return <VmConfigurationPage hostId={vmConfigurationMatch[1]} vmId={vmConfigurationMatch[2]} />;
  if (vmMatch) return <VmDetailPage hostId={vmMatch[1]} vmId={vmMatch[2]} />;
  const taskMatch = path.match(/^\/tasks\/([^/]+)$/);
  if (taskMatch) return <TaskDetailPage taskId={taskMatch[1]} />;
  const confirmMatch = path.match(/^\/hosts\/([^/]+)\/confirm$/);
  if (confirmMatch) return <HostKeyConfirmationPage hostId={confirmMatch[1]} />;
  const hostMatch = path.match(/^\/(?:manage\/)?hosts\/([^/]+)$/)
    ?? path.match(/^\/hosts\/([^/]+)\/remove$/);
  if (hostMatch) return <HostDetailPage hostId={hostMatch[1]} />;
  if (path.startsWith("/ui-preview")) return <PreviewPage />;
  return <Result status="404" title="页面不存在" extra={<Button href="/">返回总览</Button>} />;
}

function navigate(
  path: string,
  setPath: (path: string) => void,
  setDrawerOpen: (open: boolean) => void,
) {
  setDrawerOpen(false);
  if (!corePaths.has(path)) {
    window.location.assign(path);
    return;
  }
  if (window.location.pathname !== path) window.history.pushState({}, "", path);
  setPath(path);
}
