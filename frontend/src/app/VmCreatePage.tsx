import {
  Alert,
  Button,
  Card,
  Checkbox,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Radio,
  Select,
  Space,
  Spin,
  Steps,
  Typography,
} from "antd";
import { ArrowLeftOutlined, CloudServerOutlined, SafetyCertificateOutlined } from "@ant-design/icons";
import { useEffect, useState } from "react";

import type {
  TaskCreated,
  VmBlankCreateOptions,
  VmBlankCreatePreview,
  VmCreateOptions,
  VmCreatePreview,
  VmMediaCreateOptions,
  VmMediaCreatePreview,
} from "../api/contracts";
import {
  applyVmBlankCreate,
  applyVmCreate,
  loadVmBlankCreateOptions,
  loadVmCreateOptions,
  previewVmBlankCreate,
  previewVmCreate,
} from "../api/core";
import {
  applyVmMediaCreate,
  loadVmMediaCreateOptions,
  previewVmMediaCreate,
} from "../api/vmMediaCreate";
import { navigateToTask } from "./navigateToTask";
import { PageError } from "./PageState";
import { formatBytes } from "./format";

type DiskSource = "existing" | "blank" | "media";

type FormValues = {
  name?: string;
  memory_mib?: number;
  vcpus?: number;
  guest_profile?: string;
  disk_bus?: string;
  cpu_mode?: string;
  firmware?: string;
  secure_boot?: boolean;
  tpm2?: boolean;
  disk_source?: DiskSource;
  host_id?: string;
  volume_resource_id?: string;
  pool_resource_id?: string;
  disk_name?: string;
  volume_format?: string;
  capacity_gib?: number;
  media_item_id?: string;
  target_file_name?: string;
  target_capacity_gib?: number | null;
  network_resource_id?: string;
  iso_resource_id?: string;
  driver_iso_resource_id?: string;
  cloud_init?: boolean;
  cloud_hostname?: string;
  cloud_username?: string;
  cloud_password?: string;
  cloud_password_confirmation?: string;
  cloud_ssh_public_key?: string;
  cloud_network_mode?: string;
  cloud_ipv4_cidr?: string;
  cloud_ipv4_gateway?: string;
  cloud_ipv6_cidr?: string;
  cloud_ipv6_gateway?: string;
  cloud_dns_addresses?: string;
};

type UnifiedPreview =
  | { mode: "existing"; value: VmCreatePreview }
  | { mode: "blank"; value: VmBlankCreatePreview }
  | { mode: "media"; value: VmMediaCreatePreview };

type LoadedOptions = {
  existing: VmCreateOptions;
  blank: VmBlankCreateOptions;
  media: VmMediaCreateOptions;
};

export function VmCreatePage({ initialMode }: { initialMode?: DiskSource }) {
  const [form] = Form.useForm<FormValues>();
  const [options, setOptions] = useState<LoadedOptions | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [preview, setPreview] = useState<UnifiedPreview | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([loadVmCreateOptions(), loadVmBlankCreateOptions(), loadVmMediaCreateOptions()])
      .then(([existing, blank, media]) => setOptions({ existing, blank, media }))
      .catch(setError);
  }, []);

  const [modeState, setModeState] = useState<DiskSource>(initialMode ?? "existing");
  const [firmwareState, setFirmwareState] = useState("bios");
  const [secureBootState, setSecureBootState] = useState(false);
  const [hostIdState, setHostIdState] = useState<string | undefined>(undefined);
  const [cloudInitState, setCloudInitState] = useState(false);
  const [cloudNetworkModeState, setCloudNetworkModeState] = useState("dhcp");
  const mode = modeState;
  const firmware = firmwareState;
  const secureBoot = secureBootState;
  const hostId = hostIdState;
  const cloudInit = cloudInitState;
  const cloudNetworkMode = cloudNetworkModeState;

  function selectMode(value: DiskSource) {
    setModeState(value);
    setHostIdState(undefined);
    form.setFieldsValue({
      disk_source: value,
      host_id: "",
      volume_resource_id: "",
      pool_resource_id: "",
      disk_name: undefined,
      media_item_id: "",
      target_file_name: undefined,
      network_resource_id: "",
      iso_resource_id: "",
      driver_iso_resource_id: "",
    });
    setPreview(null);
    setActionError(null);
  }

  function handleValuesChange(changed: Partial<FormValues>, all: FormValues) {
    if ("firmware" in changed) {
      setFirmwareState(String(changed.firmware ?? "bios"));
      if (changed.firmware !== "uefi") {
        setSecureBootState(false);
        form.setFieldValue("secure_boot", false);
      }
    }
    if ("secure_boot" in changed) setSecureBootState(Boolean(changed.secure_boot));
    if ("host_id" in changed) {
      setHostIdState(changed.host_id ? String(changed.host_id) : undefined);
      form.setFieldsValue({
        volume_resource_id: "",
        pool_resource_id: "",
        disk_name: undefined,
        target_file_name: undefined,
        network_resource_id: "",
        iso_resource_id: "",
        driver_iso_resource_id: "",
      });
    }
    if ("cloud_init" in changed) setCloudInitState(Boolean(changed.cloud_init));
    if ("cloud_network_mode" in changed) setCloudNetworkModeState(String(changed.cloud_network_mode ?? "dhcp"));
    if ("disk_source" in changed) {
      setPreview(null);
      setActionError(null);
    }
  }

  async function submitPreview(values: FormValues) {
    if (!options) return;
    setSubmitting(true);
    setActionError(null);
    const common = {
      name: values.name ?? "",
      memory_mib: Number(values.memory_mib),
      vcpus: Number(values.vcpus),
      network_resource_id: values.network_resource_id ?? "",
      iso_resource_id: values.iso_resource_id ?? "",
      driver_iso_resource_id: values.driver_iso_resource_id ?? "",
      disk_bus: values.disk_bus ?? "virtio",
      cpu_mode: values.cpu_mode ?? "host-model",
      guest_profile: values.guest_profile ?? "linux",
      firmware: values.firmware ?? "bios",
      secure_boot: Boolean(values.secure_boot),
      tpm2: Boolean(values.tpm2),
    };
    try {
      if (mode === "existing") {
        const value = await previewVmCreate({
          ...common,
          volume_resource_id: values.volume_resource_id ?? "",
        });
        setPreview({ mode: "existing", value });
      } else if (mode === "blank") {
        const value = await previewVmBlankCreate({
          ...common,
          pool_resource_id: values.pool_resource_id ?? "",
          disk_name: values.disk_name ?? "",
          volume_format: values.volume_format ?? "qcow2",
          capacity_gib: Number(values.capacity_gib),
        });
        setPreview({ mode: "blank", value });
      } else {
        const value = await previewVmMediaCreate({
          ...common,
          media_item_id: values.media_item_id ?? "",
          pool_resource_id: values.pool_resource_id ?? "",
          target_file_name: values.target_file_name ?? "",
          target_capacity_gib: values.target_capacity_gib || null,
          cloud_init: Boolean(values.cloud_init),
          cloud_hostname: values.cloud_hostname ?? "",
          cloud_username: values.cloud_username ?? "",
          cloud_ssh_public_key: values.cloud_ssh_public_key ?? "",
          cloud_password: values.cloud_password ?? "",
          cloud_password_confirmation: values.cloud_password_confirmation ?? "",
          cloud_network_mode: values.cloud_network_mode ?? "dhcp",
          cloud_ipv4_cidr: values.cloud_ipv4_cidr ?? "",
          cloud_ipv4_gateway: values.cloud_ipv4_gateway ?? "",
          cloud_ipv6_cidr: values.cloud_ipv6_cidr ?? "",
          cloud_ipv6_gateway: values.cloud_ipv6_gateway ?? "",
          cloud_dns_addresses: (values.cloud_dns_addresses ?? "")
            .split(",")
            .map((item) => item.trim())
            .filter(Boolean),
        });
        setPreview({ mode: "media", value });
      }
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "创建计划预览失败");
    } finally {
      setSubmitting(false);
    }
  }

  async function confirmPreview() {
    if (!preview) return;
    setSubmitting(true);
    setActionError(null);
    let task: TaskCreated;
    try {
      if (preview.mode === "existing") {
        task = await applyVmCreate(preview.value);
      } else if (preview.mode === "blank") {
        task = await applyVmBlankCreate(preview.value);
      } else {
        task = await applyVmMediaCreate(preview.value);
      }
      navigateToTask(task.location);
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "创建任务失败");
      setSubmitting(false);
    }
  }

  if (error) return <PageError error={error} />;
  if (!options) return <Spin fullscreen description="正在加载可用资源" />;

  return (
    <Space className="nx-page-stack nx-create-page" orientation="vertical" size={12}>
      <div className="nx-detail-header">
        <Space orientation="vertical" size={6} className="nx-page-title">
          <Button type="link" href="/vms" icon={<ArrowLeftOutlined />} className="nx-back-link">
            返回虚拟机
          </Button>
          <Typography.Title level={2}>创建虚拟机</Typography.Title>
          <Typography.Text type="secondary">
            支持三种磁盘来源：使用已有系统盘、新建空盘或从平台镜像复制，提交前会展示完整配置差异。
          </Typography.Text>
        </Space>
      </div>

      <Steps
        responsive
        current={preview ? 1 : 0}
        items={[{ title: "配置" }, { title: "预览差异" }, { title: "确认执行" }]}
      />

      {preview ? (
        <VmCreatePreviewPanel
          preview={preview}
          loading={submitting}
          error={actionError}
          onBack={() => { setPreview(null); setActionError(null); }}
          onConfirm={confirmPreview}
        />
      ) : (
        <Form<FormValues>
          form={form}
          layout="vertical"
          requiredMark="optional"
          initialValues={{
            disk_source: initialMode ?? "existing",
            memory_mib: 2048,
            vcpus: 2,
            guest_profile: "linux",
            disk_bus: "virtio",
            cpu_mode: "host-model",
            firmware: "bios",
            volume_format: "qcow2",
            cloud_network_mode: "dhcp",
          }}
          onFinish={submitPreview}
          onValuesChange={handleValuesChange}
        >
          <Space className="nx-create-sections" orientation="vertical" size={12}>
            {actionError && <Alert type="error" showIcon title="无法生成创建计划" description={actionError} />}
            <Card title="磁盘来源">
              <Form.Item name="disk_source" rules={[{ required: true }]} style={{ marginBottom: 0 }}>
                <Radio.Group onChange={(event) => selectMode(event.target.value)}>
                  <Radio.Button value="existing">已有系统盘</Radio.Button>
                  <Radio.Button value="blank">新建空盘</Radio.Button>
                  <Radio.Button value="media">从平台镜像创建</Radio.Button>
                </Radio.Group>
              </Form.Item>
            </Card>

            <Card title="基础规格" extra={<CloudServerOutlined />}>
              <div className="nx-form-grid">
                <Form.Item label="目标节点" name="host_id" rules={[{ required: true }]} tooltip="先选择节点，后续只显示该节点上的存储、网络和 ISO。">
                  <Select aria-label="目标节点" placeholder="选择运行虚拟机的节点" options={hostsFor(options, mode)} />
                </Form.Item>
                <Form.Item label="名称" name="name" rules={[{ required: true, max: 128 }, { pattern: /^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/, message: "字母或数字开头，可包含 . _ -" }]}>
                  <Input placeholder="例如 production-web-01" />
                </Form.Item>
                <Form.Item label="客户机类型" name="guest_profile">
                  <Select options={[{ value: "linux", label: "Linux" }, { value: "windows", label: "Windows" }]} />
                </Form.Item>
                <Form.Item label="内存（MiB）" name="memory_mib" rules={[{ required: true }]}>
                  <InputNumber min={128} max={1048576} />
                </Form.Item>
                <Form.Item label="vCPU" name="vcpus" rules={[{ required: true }]}>
                  <InputNumber min={1} max={4096} />
                </Form.Item>
                <Form.Item label="系统盘 Bus" name="disk_bus">
                  <Select options={[{ value: "virtio", label: "VirtIO" }, { value: "sata", label: "SATA" }, { value: "scsi", label: "VirtIO SCSI" }]} />
                </Form.Item>
                <Form.Item label="CPU 模式" name="cpu_mode">
                  <Select options={[{ value: "host-model", label: "Host Model" }, { value: "host-passthrough", label: "Host Passthrough" }]} />
                </Form.Item>
              </div>
            </Card>

            <DiskSourceCard options={options} mode={mode} hostId={hostId} />

            <Card title="启动与安全" extra={<SafetyCertificateOutlined />}>
              <Form.Item label="固件模式" name="firmware" tooltip="UEFI 与 Secure Boot 相互独立，可使用不启用安全启动的 UEFI。">
                <Radio.Group>
                  <Radio.Button value="bios">BIOS</Radio.Button>
                  <Radio.Button value="uefi">UEFI</Radio.Button>
                </Radio.Group>
              </Form.Item>
              <Space wrap size={24} className="nx-security-options">
                <Form.Item name="secure_boot" valuePropName="checked" noStyle>
                  <Checkbox disabled={firmware !== "uefi"}>Secure Boot</Checkbox>
                </Form.Item>
                <Form.Item name="tpm2" valuePropName="checked" noStyle>
                  <Checkbox>TPM 2.0</Checkbox>
                </Form.Item>
              </Space>
              {firmware === "uefi" && !secureBoot && (
                <Alert type="info" showIcon title="当前为 UEFI 非安全启动" description="适用于不要求 Secure Boot 的操作系统或自定义引导链。" />
              )}
            </Card>

            <NetworkIsoCard options={options} hostId={hostId} />

            {mode === "media" && <CloudInitCard cloudInit={cloudInit} networkMode={cloudNetworkMode} />}

            <div className="nx-form-actions">
              <Typography.Text type="secondary">创建后保持关机，执行前仍需确认配置差异。</Typography.Text>
              <Button type="primary" htmlType="submit" loading={submitting}>预览创建计划</Button>
            </div>
          </Space>
        </Form>
      )}
    </Space>
  );
}

function hostsFor(options: LoadedOptions, mode: DiskSource) {
  const values = new Map<string, string>();
  if (mode === "existing") {
    options.existing.volumes.forEach((item) => values.set(item.host_id, item.host_name));
  } else if (mode === "blank") {
    options.blank.pools.forEach((item) => values.set(item.host_id, item.host_name));
  } else {
    options.media.targets.forEach((item) => values.set(item.host_id, item.host_name));
  }
  return Array.from(values, ([value, label]) => ({ value, label }));
}

function DiskSourceCard({ options, mode, hostId }: { options: LoadedOptions; mode: DiskSource; hostId: string | undefined }) {
  if (mode === "existing") {
    const volumes = options.existing.volumes.filter((item) => item.host_id === hostId);
    return (
      <Card title="存储与网络 · 已有系统盘">
        <Form.Item label="现有系统盘" name="volume_resource_id" rules={[{ required: true }]} tooltip="磁盘不会被复制、覆盖、扩容或删除。">
          <Select aria-label="现有系统盘" showSearch optionFilterProp="label" disabled={!hostId} placeholder="选择未被虚拟机使用的系统盘" options={volumes.map((item) => ({ value: item.id, label: `${item.pool_name} / ${item.name} · ${item.format} · ${formatBytes(item.capacity_bytes, { fixedUnit: "GiB" })}` }))} />
        </Form.Item>
      </Card>
    );
  }
  if (mode === "blank") {
    const pools = options.blank.pools.filter((item) => item.host_id === hostId);
    return (
      <Card title="存储与网络 · 新建空盘">
        <div className="nx-form-grid nx-form-grid-wide">
          <Form.Item label="目标存储池" name="pool_resource_id" rules={[{ required: true }]} tooltip="空白磁盘将创建在所选存储池中。">
            <Select showSearch optionFilterProp="label" disabled={!hostId} placeholder="先选择目标节点" options={pools.map((item) => ({ value: item.id, label: `${item.pool_name} · ${item.target_path}` }))} />
          </Form.Item>
          <Form.Item label="磁盘名称" name="disk_name" rules={[{ required: true, max: 255 }, { pattern: /^[A-Za-z0-9][A-Za-z0-9_.-]{0,254}$/, message: "字母或数字开头，可包含 . _ -" }]}>
            <Input className="nx-technical-input" placeholder="例如 web-disk-01.qcow2" />
          </Form.Item>
          <Form.Item label="格式" name="volume_format">
            <Select options={[{ value: "qcow2", label: "qcow2" }, { value: "raw", label: "raw" }]} />
          </Form.Item>
          <Form.Item label="容量（GiB）" name="capacity_gib" rules={[{ required: true }]}>
            <InputNumber min={1} max={8192} />
          </Form.Item>
        </div>
      </Card>
    );
  }
  const targets = options.media.targets.filter((item) => item.host_id === hostId);
  return (
    <Card title="存储与网络 · 从平台镜像创建">
      <div className="nx-form-grid nx-form-grid-wide">
        <Form.Item label="目标存储池" name="pool_resource_id" rules={[{ required: true }]} tooltip="镜像将复制到所选存储池后定义虚拟机。">
          <Select showSearch optionFilterProp="label" disabled={!hostId} placeholder="先选择目标节点" options={targets.map((item) => ({ value: item.id, label: `${item.pool_name} · ${item.target_path}` }))} />
        </Form.Item>
        <Form.Item label="平台镜像" name="media_item_id" rules={[{ required: true }]}>
          <Select showSearch optionFilterProp="label" placeholder="选择 qcow2/raw 镜像" options={options.media.media.map((item) => ({ value: item.id, label: `${item.file_name} · ${item.format} · ${formatBytes(item.size_bytes, { fixedUnit: "GiB" })}` }))} />
        </Form.Item>
        <Form.Item label="目标文件名" name="target_file_name" rules={[{ required: true, max: 255 }]} tooltip="禁止覆盖，扩展名必须与镜像格式一致。">
          <Input className="nx-technical-input" placeholder="example.qcow2" />
        </Form.Item>
        <Form.Item label="目标虚拟容量（GiB）" name="target_capacity_gib" tooltip="可选且只允许 grow。">
          <InputNumber min={1} max={16384} />
        </Form.Item>
      </div>
    </Card>
  );
}

function NetworkIsoCard({ options, hostId }: { options: LoadedOptions; hostId: string | undefined }) {
  const networks = options.existing.networks.filter((item) => item.host_id === hostId);
  const isos = options.existing.isos.filter((item) => item.host_id === hostId);
  return (
    <Card title="网络与安装介质">
      <div className="nx-form-grid nx-form-grid-wide">
        <Form.Item label="网络" name="network_resource_id" tooltip="仅显示与所选节点相同的可用网络。">
          <Select allowClear disabled={!hostId} placeholder="暂不添加网卡" options={networks.map((item) => ({ value: item.id, label: `${item.kind === "bridge" ? "Bridge" : "libvirt Network"} / ${item.name}` }))} />
        </Form.Item>
        <Form.Item label="安装 ISO" name="iso_resource_id">
          <Select allowClear disabled={!hostId} placeholder="不挂载安装 ISO" options={isos.map((item) => ({ value: item.id, label: `${item.pool_name} / ${item.name}` }))} />
        </Form.Item>
        <Form.Item label="VirtIO Driver ISO（Windows）" name="driver_iso_resource_id">
          <Select allowClear disabled={!hostId} placeholder="不挂载 Driver ISO" options={isos.map((item) => ({ value: item.id, label: `${item.pool_name} / ${item.name}` }))} />
        </Form.Item>
      </div>
    </Card>
  );
}

function CloudInitCard({ cloudInit, networkMode }: { cloudInit: boolean | undefined; networkMode: string | undefined }) {
  const enabled = Boolean(cloudInit);
  const staticNetwork = (networkMode ?? "dhcp") === "static";
  return (
    <Card title="Cloud Image 初始化">
      <Form.Item name="cloud_init" valuePropName="checked">
        <Checkbox>生成 NoCloud seed</Checkbox>
      </Form.Item>
      {enabled && (
        <div className="nx-form-grid">
          <Form.Item label="Hostname" name="cloud_hostname" rules={[{ required: true, max: 253 }]}><Input /></Form.Item>
          <Form.Item label="用户名" name="cloud_username" rules={[{ required: true, max: 32 }]}><Input /></Form.Item>
          <Form.Item label="密码（可选）" name="cloud_password" rules={[{ min: 12, max: 1024 }]}><Input.Password autoComplete="new-password" /></Form.Item>
          <Form.Item label="确认密码" name="cloud_password_confirmation" dependencies={["cloud_password"]} rules={[({ getFieldValue }) => ({ validator(_, value) { return !getFieldValue("cloud_password") || value === getFieldValue("cloud_password") ? Promise.resolve() : Promise.reject(new Error("两次密码不一致")); } })]}><Input.Password autoComplete="new-password" /></Form.Item>
          <Form.Item className="nx-form-span" label="SSH 公钥（可选）" name="cloud_ssh_public_key" extra="密码和 SSH 公钥至少提供一种。"><Input.TextArea rows={3} maxLength={16384} className="nx-technical-input" /></Form.Item>
          <Form.Item label="网络模式" name="cloud_network_mode"><Select options={[{ value: "dhcp", label: "DHCP" }, { value: "static", label: "静态 IPv4 / IPv6" }]} /></Form.Item>
          {staticNetwork && <>
            <Form.Item label="IPv4 CIDR" name="cloud_ipv4_cidr"><Input placeholder="192.0.2.10/24" /></Form.Item>
            <Form.Item label="IPv4 Gateway" name="cloud_ipv4_gateway"><Input placeholder="192.0.2.1" /></Form.Item>
            <Form.Item label="IPv6 CIDR" name="cloud_ipv6_cidr"><Input placeholder="2001:db8::10/64" /></Form.Item>
            <Form.Item label="IPv6 Gateway" name="cloud_ipv6_gateway"><Input placeholder="2001:db8::1" /></Form.Item>
            <Form.Item className="nx-form-span" label="DNS 地址" name="cloud_dns_addresses" rules={[{ required: true }]} extra="最多 3 个，以逗号分隔。"><Input placeholder="1.1.1.1, 9.9.9.9" /></Form.Item>
          </>}
        </div>
      )}
    </Card>
  );
}

function VmCreatePreviewPanel({
  preview,
  loading,
  error,
  onBack,
  onConfirm,
}: {
  preview: UnifiedPreview;
  loading: boolean;
  error: string | null;
  onBack: () => void;
  onConfirm: () => void;
}) {
  return (
    <Space className="nx-create-sections" orientation="vertical" size={12}>
      {error && <Alert type="error" showIcon title="无法创建任务" description={error} />}
      <div className="nx-preview-grid">
        <Card title="计划摘要">
          {preview.mode === "existing" && (() => {
            const summary = preview.value.summary;
            return <Descriptions column={1} size="small" items={[
              { key: "name", label: "名称", children: summary.name },
              { key: "host", label: "节点", children: summary.host_name },
              { key: "compute", label: "计算规格", children: `${summary.vcpus} vCPU · ${summary.memory_mib} MiB` },
              { key: "disk", label: "系统盘", children: summary.volume_name },
              { key: "network", label: "网络", children: summary.network },
              { key: "iso", label: "安装介质", children: summary.iso_name ?? "无" },
              { key: "firmware", label: "启动方式", children: firmwareLabel(summary) },
              { key: "tpm", label: "TPM 2.0", children: summary.tpm2 ? "启用" : "未启用" },
            ]} />;
          })()}
          {preview.mode === "blank" && (() => {
            const summary = preview.value.summary;
            return <Descriptions column={1} size="small" items={[
              { key: "name", label: "名称", children: summary.name },
              { key: "host", label: "节点", children: summary.host_name },
              { key: "compute", label: "计算规格", children: `${summary.vcpus} vCPU · ${summary.memory_mib} MiB` },
              { key: "pool", label: "存储池", children: summary.pool_name },
              { key: "disk", label: "空白磁盘", children: `${summary.disk_name} · ${summary.volume_format} · ${formatBytes(summary.capacity_bytes, { fixedUnit: "GiB" })}` },
              { key: "network", label: "网络", children: summary.network },
              { key: "iso", label: "安装介质", children: summary.iso_name ?? "无" },
              { key: "firmware", label: "启动方式", children: firmwareLabel(summary) },
              { key: "tpm", label: "TPM 2.0", children: summary.tpm2 ? "启用" : "未启用" },
            ]} />;
          })()}
          {preview.mode === "media" && (() => {
            const summary = preview.value.summary;
            return <Descriptions column={1} size="small" items={[
              { key: "name", label: "名称", children: summary.name },
              { key: "host", label: "节点", children: summary.host_name },
              { key: "media", label: "源镜像", children: summary.media_name },
              { key: "pool", label: "目标 Pool", children: summary.pool_name },
              { key: "target", label: "目标路径", children: <code>{summary.target_path}</code> },
              { key: "sha", label: "SHA-256", children: <code>{summary.source_sha256}</code> },
              { key: "compute", label: "计算规格", children: `${summary.vcpus} vCPU · ${summary.memory_mib} MiB` },
              { key: "capacity", label: "目标容量", children: summary.target_capacity_bytes ? formatBytes(summary.target_capacity_bytes, { fixedUnit: "GiB" }) : "保持源容量" },
              { key: "network", label: "网络", children: summary.network },
              { key: "iso", label: "安装 ISO", children: summary.iso_name ?? "无" },
              { key: "driver", label: "Driver ISO", children: summary.driver_iso_name ?? "无" },
              { key: "firmware", label: "启动方式", children: firmwareLabel(summary) },
              { key: "tpm", label: "TPM 2.0", children: summary.tpm2 ? "启用" : "未启用" },
              { key: "cloud", label: "Cloud-init", children: summary.cloud_init ?? "未启用" },
            ]} />;
          })()}
        </Card>
        <Card title="Domain XML Diff">
          <pre className="nx-code nx-code-light" aria-label="Domain XML Diff">{preview.value.diff_text}</pre>
        </Card>
      </div>
      <Alert
        type="warning"
        showIcon
        title="确认后将创建持久化任务"
        description={preview.mode === "blank" ? "先创建空白磁盘，再定义虚拟机；不会启动虚拟机或修改现有磁盘内容。" : preview.mode === "media" ? "任务将复制并校验镜像、发现新 Volume、生成可选 NoCloud seed，最后定义保持关机的虚拟机。" : "虚拟机创建后保持关机，不会启动虚拟机或修改现有磁盘内容。"}
      />
      <div className="nx-form-actions">
        <Button onClick={onBack}>返回修改</Button>
        <Button type="primary" loading={loading} onClick={onConfirm}>确认并创建任务</Button>
      </div>
    </Space>
  );
}

function firmwareLabel(summary: { firmware: string; secure_boot: boolean }): string {
  if (summary.firmware !== "uefi") return "BIOS";
  return summary.secure_boot ? "UEFI · Secure Boot" : "UEFI · 非安全启动";
}
