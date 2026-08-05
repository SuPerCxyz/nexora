import {
  Alert,
  Button,
  Card,
  Checkbox,
  Form,
  Input,
  InputNumber,
  Radio,
  Select,
  Space,
} from "antd";
import { useMemo, useState } from "react";

import type { VmMediaCreateOptions, VmMediaCreatePreviewRequest } from "../api/contracts";

type FormValues = Omit<
  VmMediaCreatePreviewRequest,
  "secure_boot" | "tpm2" | "cloud_init" | "cloud_dns_addresses"
> & {
  secure_boot?: boolean;
  tpm2?: boolean;
  cloud_init?: boolean;
  cloud_dns_addresses?: string;
};

export function VmMediaCreateForm({
  options,
  loading,
  error,
  onSubmit,
}: {
  options: VmMediaCreateOptions;
  loading: boolean;
  error: string | null;
  onSubmit: (values: VmMediaCreatePreviewRequest) => void;
}) {
  const [form] = Form.useForm<FormValues>();
  const [targetId, setTargetId] = useState("");
  const [firmware, setFirmware] = useState("bios");
  const [cloudInit, setCloudInit] = useState(false);
  const [networkMode, setNetworkMode] = useState("dhcp");
  const targetHostId = options.targets.find((item) => item.id === targetId)?.host_id ?? "";
  const networks = useMemo(
    () => options.networks.filter((item) => item.host_id === targetHostId),
    [options.networks, targetHostId],
  );
  const isos = useMemo(
    () => options.isos.filter((item) => item.host_id === targetHostId),
    [options.isos, targetHostId],
  );

  function submit(values: FormValues) {
    onSubmit({
      ...values,
      target_capacity_gib: values.target_capacity_gib || null,
      network_resource_id: values.network_resource_id || "",
      iso_resource_id: values.iso_resource_id || "",
      driver_iso_resource_id: values.driver_iso_resource_id || "",
      secure_boot: Boolean(values.secure_boot),
      tpm2: Boolean(values.tpm2),
      cloud_init: Boolean(values.cloud_init),
      cloud_hostname: values.cloud_hostname || "",
      cloud_username: values.cloud_username || "",
      cloud_ssh_public_key: values.cloud_ssh_public_key || "",
      cloud_password: values.cloud_password || "",
      cloud_password_confirmation: values.cloud_password_confirmation || "",
      cloud_network_mode: values.cloud_network_mode || "dhcp",
      cloud_ipv4_cidr: values.cloud_ipv4_cidr || "",
      cloud_ipv4_gateway: values.cloud_ipv4_gateway || "",
      cloud_ipv6_cidr: values.cloud_ipv6_cidr || "",
      cloud_ipv6_gateway: values.cloud_ipv6_gateway || "",
      cloud_dns_addresses: (values.cloud_dns_addresses ?? "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
    });
  }

  function selectTarget(value: string) {
    setTargetId(value);
    form.setFieldsValue({
      network_resource_id: "",
      iso_resource_id: "",
      driver_iso_resource_id: "",
    });
  }

  function selectFirmware(value: string) {
    setFirmware(value);
    if (value !== "uefi") form.setFieldValue("secure_boot", false);
  }

  return (
    <Form<FormValues>
      form={form}
      layout="vertical"
      requiredMark="optional"
      initialValues={{
        memory_mib: 2048,
        vcpus: 2,
        disk_bus: "virtio",
        cpu_mode: "host-model",
        guest_profile: "linux",
        firmware: "bios",
        cloud_network_mode: "dhcp",
      }}
      onFinish={submit}
    >
      <Space className="nx-create-sections" orientation="vertical" size={16}>
        {error && <Alert type="error" showIcon title="无法生成创建计划" description={error} />}
        <Card title="虚拟机与复制目标">
          <div className="nx-form-grid">
            <Form.Item label="名称" name="name" rules={[{ required: true, max: 128 }]}>
              <Input placeholder="例如 cloud-web-01" />
            </Form.Item>
            <Form.Item label="平台镜像" name="media_item_id" rules={[{ required: true }]}>
              <Select showSearch optionFilterProp="label" placeholder="选择 qcow2/raw 镜像" options={options.media.map((item) => ({ value: item.id, label: `${item.file_name} · ${item.format} · ${formatBytes(item.size_bytes)}` }))} />
            </Form.Item>
            <Form.Item label="内存（MiB）" name="memory_mib" rules={[{ required: true }]}>
              <InputNumber min={128} max={1048576} />
            </Form.Item>
            <Form.Item label="vCPU" name="vcpus" rules={[{ required: true }]}>
              <InputNumber min={1} max={4096} />
            </Form.Item>
            <Form.Item label="目标 Pool" name="pool_resource_id" rules={[{ required: true }]}>
              <Select showSearch optionFilterProp="label" onChange={selectTarget} placeholder="选择复制目标" options={options.targets.map((item) => ({ value: item.id, label: `${item.host_name} / ${item.pool_name} / ${item.target_path}` }))} />
            </Form.Item>
            <Form.Item label="目标文件名" name="target_file_name" extra="禁止覆盖，扩展名必须与镜像格式一致。" rules={[{ required: true, max: 255 }]}>
              <Input className="nx-technical-input" placeholder="example.qcow2" />
            </Form.Item>
            <Form.Item label="目标虚拟容量（GiB）" name="target_capacity_gib" extra="可选且只允许 grow。">
              <InputNumber min={1} max={16384} />
            </Form.Item>
            <Form.Item label="网络" name="network_resource_id">
              <Select allowClear disabled={!targetHostId} placeholder="暂不添加网卡" options={networks.map((item) => ({ value: item.id, label: `${item.kind === "bridge" ? "Bridge" : "libvirt Network"} / ${item.name}` }))} />
            </Form.Item>
            <Form.Item label="安装 ISO" name="iso_resource_id">
              <Select allowClear disabled={!targetHostId} placeholder="不挂载安装 ISO" options={isos.map((item) => ({ value: item.id, label: `${item.pool_name} / ${item.name}` }))} />
            </Form.Item>
            <Form.Item label="VirtIO Driver ISO" name="driver_iso_resource_id">
              <Select allowClear disabled={!targetHostId} placeholder="不挂载 Driver ISO" options={isos.map((item) => ({ value: item.id, label: `${item.pool_name} / ${item.name}` }))} />
            </Form.Item>
          </div>
        </Card>

        <Card title="平台与启动">
          <div className="nx-form-grid">
            <Form.Item label="客户机类型" name="guest_profile">
              <Select options={[{ value: "linux", label: "Linux" }, { value: "windows", label: "Windows" }]} />
            </Form.Item>
            <Form.Item label="系统盘 Bus" name="disk_bus">
              <Select options={[{ value: "virtio", label: "VirtIO" }, { value: "sata", label: "SATA" }, { value: "scsi", label: "VirtIO SCSI" }]} />
            </Form.Item>
            <Form.Item label="CPU 模式" name="cpu_mode">
              <Select options={[{ value: "host-model", label: "Host Model" }, { value: "host-passthrough", label: "Host Passthrough" }]} />
            </Form.Item>
            <Form.Item label="固件" name="firmware">
              <Radio.Group onChange={(event) => selectFirmware(event.target.value)}>
                <Radio.Button value="bios">BIOS</Radio.Button>
                <Radio.Button value="uefi">UEFI</Radio.Button>
              </Radio.Group>
            </Form.Item>
          </div>
          <Space wrap size={24}>
            <Form.Item name="secure_boot" valuePropName="checked" noStyle>
              <Checkbox disabled={firmware !== "uefi"}>Secure Boot</Checkbox>
            </Form.Item>
            <Form.Item name="tpm2" valuePropName="checked" noStyle>
              <Checkbox>TPM 2.0</Checkbox>
            </Form.Item>
          </Space>
          {firmware === "uefi" && <Alert className="nx-inline-alert" type="info" showIcon title="UEFI 默认使用非安全启动" description="仅在明确需要时启用 Secure Boot。" />}
        </Card>

        <Card title="Cloud Image 初始化">
          <Form.Item name="cloud_init" valuePropName="checked">
            <Checkbox onChange={(event) => setCloudInit(event.target.checked)}>生成 NoCloud seed</Checkbox>
          </Form.Item>
          {cloudInit && <CloudInitFields networkMode={networkMode} setNetworkMode={setNetworkMode} />}
        </Card>
        <Alert type="info" showIcon title="复制和校验完成后才定义虚拟机" description="不会覆盖已有文件，平台原镜像保持只读，失败任务可从持久化检查点恢复。" />
        <div className="nx-form-actions nx-form-actions-end">
          <Button type="primary" htmlType="submit" loading={loading}>预览复制与创建计划</Button>
        </div>
      </Space>
    </Form>
  );
}

function CloudInitFields({ networkMode, setNetworkMode }: { networkMode: string; setNetworkMode: (value: string) => void }) {
  return <div className="nx-form-grid">
    <Form.Item label="Hostname" name="cloud_hostname" rules={[{ required: true, max: 253 }]}><Input /></Form.Item>
    <Form.Item label="用户名" name="cloud_username" rules={[{ required: true, max: 32 }]}><Input /></Form.Item>
    <Form.Item label="密码（可选）" name="cloud_password" rules={[{ min: 12, max: 1024 }]}><Input.Password autoComplete="new-password" /></Form.Item>
    <Form.Item label="确认密码" name="cloud_password_confirmation" dependencies={["cloud_password"]} rules={[({ getFieldValue }) => ({ validator(_, value) { return !getFieldValue("cloud_password") || value === getFieldValue("cloud_password") ? Promise.resolve() : Promise.reject(new Error("两次密码不一致")); } })]}><Input.Password autoComplete="new-password" /></Form.Item>
    <Form.Item className="nx-form-span" label="SSH 公钥（可选）" name="cloud_ssh_public_key" extra="密码和 SSH 公钥至少提供一种。"><Input.TextArea rows={3} maxLength={16384} className="nx-technical-input" /></Form.Item>
    <Form.Item label="网络模式" name="cloud_network_mode"><Select onChange={setNetworkMode} options={[{ value: "dhcp", label: "DHCP" }, { value: "static", label: "静态 IPv4 / IPv6" }]} /></Form.Item>
    {networkMode === "static" && <>
      <Form.Item label="IPv4 CIDR" name="cloud_ipv4_cidr"><Input placeholder="192.0.2.10/24" /></Form.Item>
      <Form.Item label="IPv4 Gateway" name="cloud_ipv4_gateway"><Input placeholder="192.0.2.1" /></Form.Item>
      <Form.Item label="IPv6 CIDR" name="cloud_ipv6_cidr"><Input placeholder="2001:db8::10/64" /></Form.Item>
      <Form.Item label="IPv6 Gateway" name="cloud_ipv6_gateway"><Input placeholder="2001:db8::1" /></Form.Item>
      <Form.Item className="nx-form-span" label="DNS 地址" name="cloud_dns_addresses" rules={[{ required: true }]} extra="最多 3 个，以逗号分隔。"><Input placeholder="1.1.1.1, 9.9.9.9" /></Form.Item>
    </>}
  </div>;
}

function formatBytes(value: number): string {
  return `${(value / 1024 / 1024 / 1024).toLocaleString("zh-CN", { maximumFractionDigits: 1 })} GiB`;
}
