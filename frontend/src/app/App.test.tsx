import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

const session = {
  administrator: {
    username: "qaadmin",
    global_monospace: false,
    density: "comfortable",
    language: "zh-CN",
    timezone: "Asia/Shanghai",
  },
  csrf_token: "csrf-token",
  features: { react_preview: true, react_core_pages: true },
};

const overview = {
  host_total: 2,
  host_ready: 2,
  host_synced: 2,
  vm_total: 3,
  vm_running: 2,
  active_tasks: 0,
  failed_tasks: 0,
};

beforeEach(() => {
  window.history.replaceState({}, "", "/");
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Ant Design core application", () => {
  it("renders the status-first overview", async () => {
    stubApi({ "/internal/overview": overview });
    render(<App nonce="test-nonce" />);

    expect(await screen.findByRole("heading", { name: "总览" })).toBeInTheDocument();
    expect(screen.getByText("运行正常")).toHaveClass("nx-status-running");
    expect(screen.getByText("2 / 3")).toBeInTheDocument();
    expect(screen.getByText("子系统状态")).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("zh-CN");
    expect(screen.getByRole("img", { name: "cloud-server" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "file-image" })).toBeInTheDocument();
  });

  it("uses fixed interface typography and density preferences", async () => {
    window.history.replaceState({}, "", "/settings/account");
    stubApi({
      "/internal/account": {
        administrator: {
          ...session.administrator,
          session_timeout_minutes: 60,
        },
        login_history: [],
      },
    });
    render(<App nonce="test-nonce" />);

    expect(await screen.findByRole("heading", { name: "管理员账户" })).toBeInTheDocument();
    expect(screen.queryByLabelText("页面密度")).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: "全局使用等宽字体" })).not.toBeInTheDocument();
    expect(document.body).not.toHaveClass("nx-global-monospace", "nx-density-compact");
  });

  it("navigates to the host list without a full reload", async () => {
    stubApi({
      "/internal/overview": overview,
      "/internal/hosts?page=1&page_size=20": {
        items: [{ id: "host-1", name: "node-one", address: "192.0.2.10", ssh_port: 22, status: "ready", labels: [], last_scanned_at: null }],
        total: 1,
        page: 1,
        page_size: 20,
      },
    });
    render(<App nonce="test-nonce" />);
    await screen.findByRole("heading", { name: "总览" });

    fireEvent.click(screen.getByRole("menuitem", { name: /节点/ }));
    expect(await screen.findByRole("heading", { name: "节点" })).toBeInTheDocument();
    expect(screen.getAllByText("连接正常").length).toBeGreaterThan(0);
    expect(window.location.pathname).toBe("/hosts");
  });

  it("renders the Host Key first onboarding form", async () => {
    window.history.replaceState({}, "", "/hosts/new");
    stubApi({});
    render(<App nonce="test-nonce" />);

    expect(await screen.findByRole("heading", { name: "添加 KVM 节点" })).toBeInTheDocument();
    expect(screen.getByText("此步骤只扫描 SSH Host Key")).toBeInTheDocument();
    expect(screen.getByLabelText("SSH 私钥")).toBeInTheDocument();
  });

  it("requires explicit trusted-channel Host Key confirmation", async () => {
    window.history.replaceState({}, "", "/hosts/11111111-1111-1111-1111-111111111111/confirm");
    stubApi({
      "/internal/hosts/11111111-1111-1111-1111-111111111111/host-key-confirmation": {
        host_id: "11111111-1111-1111-1111-111111111111",
        name: "node-one",
        endpoint: "192.0.2.10:22",
        host_key_digest: "digest",
        fingerprints: [{ key_type: "ssh-ed25519", fingerprint: "SHA256:example" }],
      },
    });
    render(<App nonce="test-nonce" />);

    expect(await screen.findByText("SHA256:example")).toBeInTheDocument();
    const confirmButton = screen.getByRole("button", { name: "指纹一致，确认并开始只读探测" });
    expect(confirmButton).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: "我已通过可信渠道核对以上全部指纹" }));
    expect(confirmButton).not.toBeDisabled();
  });

  it("renders Chinese VM states and configuration", async () => {
    window.history.replaceState({}, "", "/vms");
    stubApi({
      "/internal/vms?page=1&page_size=20": {
        items: [{ resource_id: "resource-1", host_id: "host-1", native_id: "11111111-1111-1111-1111-111111111111", name: "web-01", host_name: "node-one", state: "running", status: "managed", vcpus: 4, memory_mib: 2048, last_seen_at: "2026-08-01T00:00:00Z" }],
        total: 1,
        page: 1,
        page_size: 20,
      },
    });
    render(<App nonce="test-nonce" />);

    expect((await screen.findAllByText("运行中")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("4 vCPU · 2048 MiB").length).toBeGreaterThan(0);
  });

  it("supports UEFI without enabling Secure Boot", async () => {
    window.history.replaceState({}, "", "/vms/create");
    stubApi({
      "/internal/vm-create/options": {
        volumes: [],
        networks: [],
        isos: [],
      },
    });
    render(<App nonce="test-nonce" />);

    expect(await screen.findByRole("heading", { name: "创建虚拟机" })).toBeInTheDocument();
    const secureBoot = screen.getByRole("checkbox", { name: "Secure Boot" });
    expect(secureBoot).toBeDisabled();

    fireEvent.click(screen.getByRole("radio", { name: "UEFI" }));
    expect(secureBoot).not.toBeDisabled();
    expect(secureBoot).not.toBeChecked();
    expect(screen.getByText("当前为 UEFI 非安全启动")).toBeInTheDocument();
  });

  it("supports UEFI non-secure boot for platform-image creation", async () => {
    window.history.replaceState({}, "", "/vms/create/platform-image");
    stubApi({
      "/internal/vm-create/platform-image/options": {
        media: [],
        targets: [],
        networks: [],
        isos: [],
      },
    });
    render(<App nonce="test-nonce" />);

    expect(await screen.findByRole("heading", { name: "从平台镜像创建虚拟机" })).toBeInTheDocument();
    const secureBoot = screen.getByRole("checkbox", { name: "Secure Boot" });
    expect(secureBoot).toBeDisabled();
    fireEvent.click(screen.getByRole("radio", { name: "UEFI" }));
    expect(secureBoot).not.toBeDisabled();
    expect(secureBoot).not.toBeChecked();
    expect(screen.getByText("UEFI 默认使用非安全启动")).toBeInTheDocument();
  });

  it("previews a VM creation plan without leaving React", async () => {
    window.history.replaceState({}, "", "/vms/create");
    stubApi({
      "/internal/vm-create/options": {
        volumes: [{ id: "volume-1", host_id: "host-1", host_name: "node", pool_name: "images", name: "system.qcow2", format: "qcow2", capacity_bytes: 21474836480 }],
        networks: [],
        isos: [],
      },
      "/internal/vm-create/preview": {
        plan_id: "plan-1",
        confirmation_token: "confirmation",
        host_id: "host-1",
        vm_uuid: "11111111-1111-1111-1111-111111111111",
        diff_text: "+ <domain/>",
        summary: { name: "react-vm", host_name: "node", vcpus: 2, memory_mib: 2048, volume_name: "system.qcow2", network: "无网卡", iso_name: null, firmware: "uefi", secure_boot: false, tpm2: false },
      },
    });
    render(<App nonce="test-nonce" />);
    await screen.findByRole("heading", { name: "创建虚拟机" });

    fireEvent.change(screen.getByRole("textbox", { name: "名称" }), { target: { value: "react-vm" } });
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "目标节点" }));
    fireEvent.click(await screen.findByText("node"));
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "现有系统盘" }));
    fireEvent.click(await screen.findByText(/system\.qcow2/));
    fireEvent.click(screen.getByRole("radio", { name: "UEFI" }));
    fireEvent.click(screen.getByRole("button", { name: "预览创建计划" }));

    expect(await screen.findByText("Domain XML Diff")).toBeInTheDocument();
    expect(screen.getByText("UEFI · 非安全启动")).toBeInTheDocument();
    expect(screen.getByLabelText("Domain XML Diff")).toHaveTextContent("+ <domain/>");
  }, 10000);

  it("opens the mobile navigation drawer", async () => {
    stubApi({ "/internal/overview": overview });
    render(<App nonce="test-nonce" />);
    await screen.findByRole("heading", { name: "总览" });

    fireEvent.click(screen.getByRole("button", { name: "打开主导航" }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("shows the login action when the session expires", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: "authentication_required", message: "管理员会话已失效", field_errors: {}, conflict: null, task_id: null }), { status: 401 })));
    render(<App nonce="test-nonce" />);

    await waitFor(() => expect(screen.getByText("管理员会话已失效")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: "前往登录" })).toHaveAttribute("href", "/login");
  });

  it("renders the migrated host detail", async () => {
    window.history.replaceState({}, "", "/hosts/11111111-1111-1111-1111-111111111111");
    stubApi({
      "/internal/hosts/11111111-1111-1111-1111-111111111111": {
        host: { id: "11111111-1111-1111-1111-111111111111", name: "node-one", address: "192.0.2.10", ssh_port: 22, status: "ready", labels: [], last_scanned_at: null },
        ssh_username: "root",
        libvirt_uri: "qemu:///system",
        resource_counts: { virtual_machine: 1 },
        virtual_machines: [],
        hardware: {
          manufacturer: "Example Vendor", model: "Example Server", os_name: "Rocky Linux 9.7",
          kernel: "5.14.0", architecture: "x86_64", cpu_model: "Example CPU",
          logical_cpus: 16, sockets: 1, cores_per_socket: 8, threads_per_core: 2,
          numa_nodes: 1, memory_bytes: 34359738368,
        },
        network_adapters: [{ name: "eno1", mac: "00:11:22:33:44:55", kind: "physical", state: "up", management: true }],
        features: [
          { key: "virtualization", name: "虚拟机管理", status: "supported", description: "查看并控制 libvirt 虚拟机" },
          { key: "pcie_passthrough", name: "PCIe 设备直通", status: "supported", description: "已发现 2 个可直通 PCIe 设备" },
          { key: "open_vswitch", name: "Open vSwitch", status: "unsupported", description: "发现 Open vSwitch 网络" },
        ],
        latest_metrics: null,
        manage_url: "/manage/hosts/11111111-1111-1111-1111-111111111111",
      },
    });
    render(<App nonce="test-nonce" />);

    expect(await screen.findByRole("heading", { name: "node-one" })).toBeInTheDocument();
    expect(screen.getByText("硬件概览")).toBeInTheDocument();
    expect(screen.getByText("Example CPU")).toBeInTheDocument();
    expect(screen.getByText("00:11:22:33:44:55")).toBeInTheDocument();
    expect(screen.getByText("虚拟机管理")).toBeInTheDocument();
    expect(screen.getByText("PCIe 设备直通")).toBeInTheDocument();
    expect(screen.getByText("已发现 2 个可直通 PCIe 设备")).toBeInTheDocument();
    expect(screen.getByText("不支持")).toHaveClass("nx-status-stopped");
    expect(screen.queryByText("能力探测")).not.toBeInTheDocument();
    expect(screen.getByText("子系统状态")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "刷新节点信息" })).toHaveClass("nx-btn-info");
    expect(screen.getByRole("button", { name: "移除节点" })).toHaveClass("nx-btn-danger");
  });

  it("renders devices and formatted XML on the VM detail", async () => {
    window.history.replaceState({}, "", "/hosts/11111111-1111-1111-1111-111111111111/vms/22222222-2222-2222-2222-222222222222");
    stubApi({
      "/internal/hosts/11111111-1111-1111-1111-111111111111/vms/22222222-2222-2222-2222-222222222222": {
        vm: { resource_id: "vm-1", host_id: "11111111-1111-1111-1111-111111111111", native_id: "22222222-2222-2222-2222-222222222222", name: "web-01", host_name: "node-one", state: "running", status: "managed", vcpus: 4, memory_mib: 2048, last_seen_at: "2026-08-01T00:00:00Z" },
        active: true,
        persistent: true,
        autostart: true,
        maximum_vcpus: 8,
        configuration_status: "managed",
        disks: [{ type: "file", device: "disk", source: "/images/web.qcow2", target: "vda", bus: "virtio", format: "qcow2", readonly: false, shareable: false }],
        interfaces: [],
        host_devices: [{ type: "pci", address: "0000:05:00.0", category: "网卡", name: "Intel Corporation · I211 Gigabit Network Connection", driver: "vfio-pci", iommu_group: "17" }],
        snapshots: [],
        metrics: [],
        xml: "<domain>\n  <name>web-01</name>\n</domain>\n",
        manage_url: "/manage/hosts/11111111-1111-1111-1111-111111111111/vms/22222222-2222-2222-2222-222222222222",
      },
      "/internal/hosts/11111111-1111-1111-1111-111111111111/vms/22222222-2222-2222-2222-222222222222/guest-agent": {
        state: "connected",
        channel_configured: true,
        hostname: "web-01",
        addresses: [{ interface: "eth0", address: "192.0.2.20", prefix: 24, family: "IPv4", mac: "52:54:00:12:34:56" }],
        message: null,
      },
    });
    render(<App nonce="test-nonce" />);

    expect(await screen.findByRole("heading", { name: "web-01" })).toBeInTheDocument();
    expect(screen.getByText("4 / 8 vCPU")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /配\s*置/ })).toHaveAttribute(
      "href",
      "/hosts/11111111-1111-1111-1111-111111111111/vms/22222222-2222-2222-2222-222222222222/config",
    );
    expect(screen.getByRole("button", { name: "VNC 控制台" })).toHaveClass("nx-btn-special");
    expect(screen.getByRole("button", { name: "正常关机" })).toHaveClass("nx-btn-warning");
    expect(screen.getByRole("button", { name: "正常重启" })).toHaveClass("nx-btn-warning");
    expect(screen.getByRole("button", { name: /暂\s*停/ })).toHaveClass("nx-btn-warning");
    expect(screen.getByRole("button", { name: "保存运行状态" })).toHaveClass("nx-btn-info");
    expect(screen.getByRole("button", { name: "强制操作" })).toHaveClass("nx-btn-danger");
    expect(screen.getByRole("button", { name: "强制操作" }).parentElement).toHaveClass(
      "nx-vm-action-buttons",
    );
    expect(screen.getByText("1 个透传网卡")).toBeInTheDocument();
    expect(screen.getByText("直通设备")).toBeInTheDocument();
    expect(screen.getByText("Intel Corporation · I211 Gigabit Network Connection")).toBeInTheDocument();
    expect(screen.getByText("0000:05:00.0")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "XML" }));
    expect(screen.getByText(/<domain>/)).toBeInTheDocument();
  }, 10000);

  it("renders the legacy VM manage URL with React configuration", async () => {
    window.history.replaceState({}, "", "/manage/hosts/11111111-1111-1111-1111-111111111111/vms/22222222-2222-2222-2222-222222222222");
    stubApi({
      "/internal/hosts/11111111-1111-1111-1111-111111111111/vms/22222222-2222-2222-2222-222222222222/configuration": {
        vm: { name: "openwrt", host_id: "11111111-1111-1111-1111-111111111111", native_id: "22222222-2222-2222-2222-222222222222", state: "shutoff", active: false, persistent: true },
        base: { resource_id: "vm-1", generation: 3, persistent_hash: "a".repeat(64) },
        cpu: { current_vcpus: 4, maximum_vcpus: 4, sockets: 1, dies: 1, clusters: 1, cores: 4, threads: 1 },
        memory: { current_kib: 1048576, maximum_kib: 1048576, hugepages: false, locked: false, source_type: null, access_mode: null, allocation_mode: null, discard: false },
        advanced: null,
        disks: [{ target: "vda", device: "disk", source: "/images/openwrt.img", bus: "virtio" }],
        storage_volumes: [],
        platform_isos: [],
        platform_iso_enabled: false,
        host_devices: [{ resource_id: "pci-1", type: "pci_device", name: "Intel I211", address: "0000:05:00.0", status: "read_only" }],
        shared_directory_roots: [],
      },
    });
    render(<App nonce="test-nonce" />);

    expect(await screen.findByRole("heading", { name: "openwrt · 配置" })).toBeInTheDocument();
    expect(screen.getByText("计算与内存")).toBeInTheDocument();
    expect(screen.getByText("磁盘与光驱")).toBeInTheDocument();
    expect(screen.getByText("直通设备与共享目录")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "预览 CPU Diff" })).toBeInTheDocument();
  }, 10000);

  it("renders the React task center with Chinese status tags", async () => {
    window.history.replaceState({}, "", "/tasks");
    stubApi({
      "/internal/tasks": {
        items: [{
          id: "task-1", title: "启动虚拟机 · web-01", task_type: "vm.lifecycle",
          status: "running", progress: 50, current_step: 1, total_steps: 3,
          message: null, error_message: null, created_at: "2026-08-01T00:00:00Z",
          started_at: "2026-08-01T00:00:01Z", finished_at: null,
          resumable: false, retry_count: 0, max_retries: 0,
        }],
      },
    });
    render(<App nonce="test-nonce" />);

    expect(await screen.findByRole("heading", { name: "任务中心" }, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "启动虚拟机 · web-01" })).toHaveAttribute("href", "/tasks/task-1");
    expect(screen.getByText("执行中")).toHaveClass("nx-status-starting");
  });
});

function stubApi(responses: Record<string, object>) {
  vi.stubGlobal("fetch", vi.fn().mockImplementation((input: RequestInfo | URL) => {
    const path = typeof input === "string" ? input : input.toString();
    const payload = path === "/internal/session" ? session : responses[path];
    if (!payload) return Promise.reject(new Error(`Unexpected request: ${path}`));
    return Promise.resolve(new Response(JSON.stringify(payload)));
  }));
}
