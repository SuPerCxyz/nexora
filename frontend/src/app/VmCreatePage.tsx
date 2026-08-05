import {
  Alert,
  Button,
  Card,
  Checkbox,
  Descriptions,
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
import { useEffect, useMemo, useState } from "react";

import type { VmCreateOptions, VmCreatePreview } from "../api/contracts";
import { applyVmCreate, loadVmCreateOptions, previewVmCreate } from "../api/core";
import { PageError } from "./PageState";

export function VmCreatePage() {
  const [options, setOptions] = useState<VmCreateOptions | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [hostId, setHostId] = useState("");
  const [volumeId, setVolumeId] = useState("");
  const [networkId, setNetworkId] = useState("");
  const [isoId, setIsoId] = useState("");
  const [driverIsoId, setDriverIsoId] = useState("");
  const [firmware, setFirmware] = useState("bios");
  const [guestProfile, setGuestProfile] = useState("linux");
  const [diskBus, setDiskBus] = useState("virtio");
  const [cpuMode, setCpuMode] = useState("host-model");
  const [secureBoot, setSecureBoot] = useState(false);
  const [tpm2, setTpm2] = useState(false);
  const [preview, setPreview] = useState<VmCreatePreview | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    loadVmCreateOptions().then(setOptions).catch(setError);
  }, []);

  const selectedHostId = hostId;
  const hosts = useMemo(() => {
    const values = new Map<string, string>();
    options?.volumes.forEach((item) => values.set(item.host_id, item.host_name));
    return Array.from(values, ([value, label]) => ({ value, label }));
  }, [options]);
  const volumes = useMemo(
    () => options?.volumes.filter((item) => item.host_id === selectedHostId) ?? [],
    [options, selectedHostId],
  );
  const networks = useMemo(
    () => options?.networks.filter((item) => item.host_id === selectedHostId) ?? [],
    [options, selectedHostId],
  );
  const isos = useMemo(
    () => options?.isos.filter((item) => item.host_id === selectedHostId) ?? [],
    [options, selectedHostId],
  );

  function selectVolume(value: string) {
    setVolumeId(value);
  }

  function selectHost(value: string) {
    setHostId(value);
    setVolumeId("");
    setNetworkId("");
    setIsoId("");
    setDriverIsoId("");
  }

  function selectFirmware(value: string) {
    setFirmware(value);
    if (value !== "uefi") setSecureBoot(false);
  }

  async function submitPreview(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = new FormData(event.currentTarget);
    setSubmitting(true);
    setActionError(null);
    try {
      setPreview(await previewVmCreate({
        name: String(values.get("name") ?? ""),
        memory_mib: Number(values.get("memory_mib")),
        vcpus: Number(values.get("vcpus")),
        volume_resource_id: volumeId,
        network_resource_id: networkId,
        iso_resource_id: isoId,
        driver_iso_resource_id: driverIsoId,
        disk_bus: diskBus,
        cpu_mode: cpuMode,
        guest_profile: guestProfile,
        firmware,
        secure_boot: secureBoot,
        tpm2,
      }));
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
    try {
      const task = await applyVmCreate(preview);
      window.location.assign(task.location);
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "创建任务失败");
      setSubmitting(false);
    }
  }

  if (error) return <PageError error={error} />;
  if (!options) return <Spin fullscreen description="正在加载可用资源" />;

  return (
    <Space className="nx-page-stack nx-create-page" orientation="vertical" size={24}>
      <div className="nx-detail-header">
        <Space orientation="vertical" size={6}>
          <Button type="link" href="/vms" icon={<ArrowLeftOutlined />} className="nx-back-link">
            返回虚拟机
          </Button>
          <Typography.Title level={2}>创建虚拟机</Typography.Title>
          <Typography.Text type="secondary">
            使用已纳管的系统盘创建虚拟机，提交前会展示完整配置差异。
          </Typography.Text>
        </Space>
        <Space wrap>
          <Button className="nx-btn-info" href="/vms/create/blank-disk">从空白磁盘创建</Button>
          <Button className="nx-btn-info" href="/vms/create/platform-image">从平台镜像创建</Button>
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
      <form onSubmit={submitPreview}>
        <input type="hidden" name="volume_resource_id" value={volumeId} />
        <input type="hidden" name="network_resource_id" value={networkId} />
        <input type="hidden" name="iso_resource_id" value={isoId} />
        <input type="hidden" name="driver_iso_resource_id" value={driverIsoId} />
        <input type="hidden" name="firmware" value={firmware} />
        <input type="hidden" name="guest_profile" value={guestProfile} />
        <input type="hidden" name="disk_bus" value={diskBus} />
        <input type="hidden" name="cpu_mode" value={cpuMode} />
        <input type="hidden" name="secure_boot" value={secureBoot ? "on" : ""} />
        <input type="hidden" name="tpm2" value={tpm2 ? "on" : ""} />

        <Space className="nx-create-sections" orientation="vertical" size={16}>
          {actionError && <Alert type="error" showIcon title="无法生成创建计划" description={actionError} />}
          <Card title="基础规格" extra={<CloudServerOutlined />}>
            <div className="nx-form-grid">
              <Field label="目标节点" hint="先选择节点，后续只显示该节点上的存储、网络和 ISO。">
                <Select aria-label="目标节点" value={hostId || undefined} onChange={selectHost} placeholder="选择运行虚拟机的节点" options={hosts} />
              </Field>
              <Field label="名称" hint="字母或数字开头，可包含 . _ -">
                <Input aria-label="名称" name="name" required maxLength={128} pattern="[A-Za-z0-9][A-Za-z0-9_.-]{0,127}" placeholder="例如 production-web-01" />
              </Field>
              <Field label="客户机类型">
                <Select aria-label="客户机类型" value={guestProfile} onChange={setGuestProfile} options={[{ value: "linux", label: "Linux" }, { value: "windows", label: "Windows" }]} />
              </Field>
              <Field label="内存（MiB）">
                <InputNumber aria-label="内存（MiB）" name="memory_mib" min={128} max={1048576} defaultValue={2048} required />
              </Field>
              <Field label="vCPU">
                <InputNumber aria-label="vCPU" name="vcpus" min={1} max={4096} defaultValue={2} required />
              </Field>
              <Field label="系统盘 Bus">
                <Select aria-label="系统盘 Bus" value={diskBus} onChange={setDiskBus} options={[{ value: "virtio", label: "VirtIO" }, { value: "sata", label: "SATA" }, { value: "scsi", label: "VirtIO SCSI" }]} />
              </Field>
              <Field label="CPU 模式">
                <Select aria-label="CPU 模式" value={cpuMode} onChange={setCpuMode} options={[{ value: "host-model", label: "Host Model" }, { value: "host-passthrough", label: "Host Passthrough" }]} />
              </Field>
            </div>
          </Card>

          <Card title="启动与安全" extra={<SafetyCertificateOutlined />}>
            <Field label="固件模式" hint="UEFI 与 Secure Boot 相互独立，可使用不启用安全启动的 UEFI。">
              <Radio.Group aria-label="固件模式" value={firmware} onChange={(event) => selectFirmware(event.target.value)}>
                <Radio.Button value="bios">BIOS</Radio.Button>
                <Radio.Button value="uefi">UEFI</Radio.Button>
              </Radio.Group>
            </Field>
            <Space wrap size={24} className="nx-security-options">
              <Checkbox checked={secureBoot} disabled={firmware !== "uefi"} onChange={(event) => setSecureBoot(event.target.checked)}>
                Secure Boot
              </Checkbox>
              <Checkbox checked={tpm2} onChange={(event) => setTpm2(event.target.checked)}>TPM 2.0</Checkbox>
            </Space>
            {firmware === "uefi" && !secureBoot && (
              <Alert type="info" showIcon title="当前为 UEFI 非安全启动" description="适用于不要求 Secure Boot 的操作系统或自定义引导链。" />
            )}
          </Card>

          <Card title="存储与网络">
            <div className="nx-form-grid nx-form-grid-wide">
              <Field label="现有系统盘" hint="磁盘不会被复制、覆盖、扩容或删除。">
                <Select aria-label="现有系统盘" showSearch value={volumeId || undefined} onChange={selectVolume} disabled={!selectedHostId} placeholder="选择未被虚拟机使用的系统盘" optionFilterProp="label" options={volumes.map((item) => ({ value: item.id, label: `${item.pool_name} / ${item.name} · ${item.format} · ${formatBytes(item.capacity_bytes)}` }))} />
              </Field>
              <Field label="网络" hint="仅显示与系统盘相同节点的可用网络。">
                <Select aria-label="网络" allowClear value={networkId || undefined} onChange={(value) => setNetworkId(value ?? "")} disabled={!selectedHostId} placeholder="暂不添加网卡" options={networks.map((item) => ({ value: item.id, label: `${item.kind === "bridge" ? "Bridge" : "libvirt Network"} / ${item.name}` }))} />
              </Field>
              <Field label="安装 ISO">
                <Select aria-label="安装 ISO" allowClear value={isoId || undefined} onChange={(value) => setIsoId(value ?? "")} disabled={!selectedHostId} placeholder="不挂载安装 ISO" options={isos.map((item) => ({ value: item.id, label: `${item.pool_name} / ${item.name}` }))} />
              </Field>
              <Field label="VirtIO Driver ISO（Windows）">
                <Select aria-label="VirtIO Driver ISO" allowClear value={driverIsoId || undefined} onChange={(value) => setDriverIsoId(value ?? "")} disabled={!selectedHostId} placeholder="不挂载 Driver ISO" options={isos.map((item) => ({ value: item.id, label: `${item.pool_name} / ${item.name}` }))} />
              </Field>
            </div>
          </Card>

          <div className="nx-form-actions">
            <Typography.Text type="secondary">创建后保持关机，执行前仍需确认配置差异。</Typography.Text>
            <Button type="primary" htmlType="submit" loading={submitting} disabled={!volumeId}>预览创建计划</Button>
          </div>
        </Space>
      </form>
      )}
    </Space>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return <label className="nx-form-field"><span>{label}</span>{children}{hint && <small>{hint}</small>}</label>;
}

function formatBytes(value: number): string {
  const gibibytes = value / 1024 / 1024 / 1024;
  return `${gibibytes.toLocaleString("zh-CN", { maximumFractionDigits: 1 })} GiB`;
}

function VmCreatePreviewPanel({
  preview,
  loading,
  error,
  onBack,
  onConfirm,
}: {
  preview: VmCreatePreview;
  loading: boolean;
  error: string | null;
  onBack: () => void;
  onConfirm: () => void;
}) {
  const summary = preview.summary;
  return (
    <Space className="nx-create-sections" orientation="vertical" size={16}>
      {error && <Alert type="error" showIcon title="无法创建任务" description={error} />}
      <div className="nx-preview-grid">
        <Card title="计划摘要">
          <Descriptions column={1} size="small" items={[
            { key: "name", label: "名称", children: summary.name },
            { key: "host", label: "节点", children: summary.host_name },
            { key: "compute", label: "计算规格", children: `${summary.vcpus} vCPU · ${summary.memory_mib} MiB` },
            { key: "disk", label: "系统盘", children: summary.volume_name },
            { key: "network", label: "网络", children: summary.network },
            { key: "iso", label: "安装介质", children: summary.iso_name ?? "无" },
            { key: "firmware", label: "启动方式", children: firmwareLabel(summary) },
            { key: "tpm", label: "TPM 2.0", children: summary.tpm2 ? "启用" : "未启用" },
          ]} />
        </Card>
        <Card title="Domain XML Diff">
          <pre className="nx-code nx-code-light" aria-label="Domain XML Diff">{preview.diff_text}</pre>
        </Card>
      </div>
      <Alert type="warning" showIcon title="确认后将创建持久化任务" description="虚拟机创建后保持关机，不会启动虚拟机或修改现有磁盘内容。" />
      <div className="nx-form-actions">
        <Button onClick={onBack}>返回修改</Button>
        <Button type="primary" loading={loading} onClick={onConfirm}>确认并创建任务</Button>
      </div>
    </Space>
  );
}

function firmwareLabel(summary: VmCreatePreview["summary"]): string {
  if (summary.firmware !== "uefi") return "BIOS";
  return summary.secure_boot ? "UEFI · Secure Boot" : "UEFI · 非安全启动";
}
