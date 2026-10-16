import { useState, useEffect, useRef } from 'react';
import {
  Table,
  Button,
  Drawer,
  Form,
  Input,
  Select,
  InputNumber,
  DatePicker,
  Popconfirm,
  message,
  Empty,
  Skeleton,
  Typography,
  Space,
  Tag,
  Alert,
  Spin,
  Card,
  Modal,
} from 'antd';
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  CameraOutlined,
  ReloadOutlined,
  CloseOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import {
  getMedicines,
  createMedicine,
  updateMedicine,
  deleteMedicine,
  recognizeMedicineImage,
  lookupBarcode,
  type Medicine,
  type PaginatedMedicines,
  type OcrRecognitionResult,
} from '../api/medicineApi';
import { PAGE_SIZE, DRUG_STATUS_COLOR } from '../constants';
import StatusTag from '../components/StatusTag';
import { useIsMobile } from '../hooks/useIsMobile';

const { Title } = Typography;

interface DetectedBarcode {
  rawValue: string;
}

interface CameraBarcodeDetector {
  detect(source: HTMLVideoElement): Promise<DetectedBarcode[]>;
}

interface CameraBarcodeDetectorConstructor {
  new (options?: { formats?: string[] }): CameraBarcodeDetector;
  getSupportedFormats?: () => Promise<string[]>;
}

function getBarcodeDetectorConstructor(): CameraBarcodeDetectorConstructor | undefined {
  return (window as Window & { BarcodeDetector?: CameraBarcodeDetectorConstructor }).BarcodeDetector;
}

const MEDICINE_TYPES = ['西药', '中成药', '中药饮片', '保健品'];
const MEDICINE_STATUS = ['充足', '低库存', '已过期'];

interface FormValues {
  name: string;
  type: string;
  status?: string;
  dosage?: string;
  notes?: string;
  quantity?: number;
  expiry_date?: dayjs.Dayjs;
  barcode?: string;
}

export default function MedicineList() {
  const isMobile = useIsMobile();
  const [medicines, setMedicines] = useState<Medicine[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingMedicine, setEditingMedicine] = useState<Medicine | null>(
    null,
  );
  const [form] = Form.useForm<FormValues>();
  const [pagination, setPagination] = useState({ current: 1, pageSize: PAGE_SIZE, total: 0 });
  const [ocrLoading, setOcrLoading] = useState(false);
  const [lowConfidenceFields, setLowConfidenceFields] = useState<Set<string>>(new Set());
  const fileInputRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const cameraStreamRef = useRef<MediaStream | null>(null);
  const scanFrameRef = useRef<number | null>(null);
  const detectingRef = useRef(false);
  const [scannerOpen, setScannerOpen] = useState(false);
  const [scannerMessage, setScannerMessage] = useState('');
  const [scannerStarting, setScannerStarting] = useState(false);

  const stopBarcodeScanner = () => {
    if (scanFrameRef.current !== null) {
      window.cancelAnimationFrame(scanFrameRef.current);
      scanFrameRef.current = null;
    }
    cameraStreamRef.current?.getTracks().forEach((track) => track.stop());
    cameraStreamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setScannerStarting(false);
  };

  const closeBarcodeScanner = () => {
    stopBarcodeScanner();
    setScannerOpen(false);
  };

  useEffect(() => () => {
    if (scanFrameRef.current !== null) window.cancelAnimationFrame(scanFrameRef.current);
    cameraStreamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);

  useEffect(() => {
    if (!drawerOpen) closeBarcodeScanner();
    // Drawer closure must stop the camera even when caused by save or navigation.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drawerOpen]);

  useEffect(() => {
    if (!scannerOpen) {
      stopBarcodeScanner();
      return;
    }
    let cancelled = false;
    const start = async () => {
      const Detector = getBarcodeDetectorConstructor();
      if (!Detector) {
        setScannerMessage('当前浏览器不支持相机条码识别，请关闭此窗口后手动输入条形码。');
        return;
      }
      if (!navigator.mediaDevices?.getUserMedia || !window.isSecureContext) {
        setScannerMessage('相机需要安全连接（HTTPS 或 localhost）及浏览器权限，请手动输入条形码。');
        return;
      }

      setScannerStarting(true);
      setScannerMessage('请允许使用相机，并将药品条形码放入取景框。');
      try {
        const formats = Detector.getSupportedFormats
          ? await Detector.getSupportedFormats()
          : ['ean_13', 'ean_8'];
        const supported = ['ean_13', 'ean_8'].filter((format) => formats.includes(format));
        if (supported.length === 0) {
          setScannerMessage('当前浏览器无法识别 EAN-8/EAN-13 条码，请手动输入条形码。');
          setScannerStarting(false);
          return;
        }
        const detector = new Detector({ formats: supported });
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: { ideal: 'environment' } },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        cameraStreamRef.current = stream;
        const video = videoRef.current;
        if (!video) return;
        video.srcObject = stream;
        await video.play();
        setScannerStarting(false);

        const scan = async () => {
          if (cancelled || !cameraStreamRef.current || !videoRef.current) return;
          if (!detectingRef.current && videoRef.current.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
            detectingRef.current = true;
            try {
              const hits = await detector.detect(videoRef.current);
              const barcode = hits.find((hit) => hit.rawValue)?.rawValue.trim();
              if (barcode) {
                cancelled = true;
                stopBarcodeScanner();
                setScannerOpen(false);
                form.setFieldValue('barcode', barcode);
                try {
                  const result = await lookupBarcode(barcode);
                  if (result.valid) message.success('扫码成功，条形码校验通过；保存药品后将关联此条码');
                  else message.warning(result.reason ?? '已填入扫码结果，但条形码校验未通过，请核对后再保存');
                } catch {
                  message.warning('已填入扫码结果，但条形码校验服务暂不可用，请手动核对后再保存');
                }
                return;
              }
            } catch {
              setScannerMessage('条码识别暂时失败，请调整药品位置，或手动输入条形码。');
            } finally {
              detectingRef.current = false;
            }
          }
          if (!cancelled) scanFrameRef.current = window.requestAnimationFrame(() => { void scan(); });
        };
        scanFrameRef.current = window.requestAnimationFrame(() => { void scan(); });
      } catch (error) {
        setScannerStarting(false);
        stopBarcodeScanner();
        setScannerMessage(error instanceof DOMException && error.name === 'NotAllowedError'
          ? '相机权限未获允许，请在浏览器设置中允许相机，或手动输入条形码。'
          : '无法启动相机，请检查设备及浏览器权限，或手动输入条形码。');
      }
    };
    void start();
    return () => {
      cancelled = true;
      if (scanFrameRef.current !== null) window.cancelAnimationFrame(scanFrameRef.current);
      scanFrameRef.current = null;
      cameraStreamRef.current?.getTracks().forEach((track) => track.stop());
      cameraStreamRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scannerOpen]);

  const loadMedicines = async (page?: number) => {
    setLoading(true);
    setLoadError(false);
    try {
      const data: PaginatedMedicines = await getMedicines({
        page: page ?? pagination.current,
        pageSize: pagination.pageSize,
      });
      setMedicines(data.items);
      setPagination({
        current: data.page,
        pageSize: data.pageSize,
        total: data.total,
      });
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadMedicines(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleAdd = () => {
    setEditingMedicine(null);
    setLowConfidenceFields(new Set());
    form.resetFields();
    setDrawerOpen(true);
  };

  const handlePhotoAdd = () => {
    fileInputRef.current?.click();
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = '';

    setOcrLoading(true);
    try {
      const result: OcrRecognitionResult = await recognizeMedicineImage(file);

      setEditingMedicine(null);
      setLowConfidenceFields(new Set());
      form.resetFields();

      const lowFields = new Set<string>();

      if (result.name) {
        form.setFieldValue('name', result.name);
        if (result.confidence === 'low') lowFields.add('name');
      }
      if (result.dosage_instructions) {
        form.setFieldValue('dosage', result.dosage_instructions);
        if (result.confidence === 'low') lowFields.add('dosage');
      }
      if (result.specification || result.raw_text) {
        const noteParts: string[] = [];
        if (result.specification) noteParts.push(`规格：${result.specification}`);
        if (result.raw_text) noteParts.push(`OCR识别原文：\n${result.raw_text.substring(0, 200)}`);
        form.setFieldValue('notes', noteParts.join('\n'));
      }

      setLowConfidenceFields(lowFields);
      setDrawerOpen(true);

      if (result.confidence === 'high') {
        message.success('识别成功，请确认信息后保存');
      } else if (result.confidence === 'medium') {
        message.warning('部分识别，请核实标黄字段');
      } else {
        message.warning('识别置信度较低，请仔细核实');
      }
    } catch {
      message.error('识别失败，请重试或手动添加');
    } finally {
      setOcrLoading(false);
    }
  };

  const handleEdit = (record: Medicine) => {
    setEditingMedicine(record);
    setLowConfidenceFields(new Set());
    form.setFieldsValue({
      name: record.name,
      type: record.type,
      status: record.status,
      dosage: record.dosage,
      notes: record.notes,
      quantity: record.quantity,
      expiry_date: record.expiry_date ? dayjs(record.expiry_date) : undefined,
      barcode: record.barcode,
    });
    setDrawerOpen(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      if (editingMedicine) {
        await updateMedicine(editingMedicine.id, {
          ...values,
          expiry_date: values.expiry_date?.format('YYYY-MM-DD'),
        });
        message.success('更新成功');
      } else {
        await createMedicine({
          ...values,
          expiry_date: values.expiry_date?.format('YYYY-MM-DD'),
        });
        message.success('添加成功');
      }
      setDrawerOpen(false);
      loadMedicines(pagination.current);
    } catch (err) {
      // antd 表单校验错误为普通对象（含 errorFields），不弹提示；API 失败（Error）才提示
      if (err instanceof Error && err.message.includes('未授权')) {
        message.error('登录已过期，请重新登录');
      } else if (err instanceof Error) {
        message.error('保存失败，请检查网络后重试');
      }
    }
  };

  const handleBarcodeCheck = async (barcode: string) => {
    if (!barcode.trim()) {
      message.warning('请先输入条形码');
      return;
    }
    try {
      const result = await lookupBarcode(barcode.trim());
      if (result.valid) message.success(`${result.format ?? '条形码'}校验通过，保存后会关联到药品`);
      else message.warning(result.reason ?? '条形码格式无效');
    } catch {
      message.error('条形码校验失败，请稍后重试');
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteMedicine(id);
      message.success('删除成功');
      loadMedicines(pagination.current);
    } catch (err) {
      if (err instanceof Error && err.message.includes('未授权')) {
        message.error('登录已过期，请重新登录');
      } else {
        message.error('删除失败');
      }
    }
  };

  const columns = [
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '类型', dataIndex: 'type', key: 'type' },
    {
      title: '数量',
      dataIndex: 'quantity',
      key: 'quantity',
      width: 80,
      render: (qty: number | undefined) => {
        if (qty == null) return '—';
        return (
          <Tag color={qty <= 5 ? 'orange' : 'green'}>
            {qty <= 5 ? `低库存 ${qty}` : qty}
          </Tag>
        );
      },
    },
    {
      title: '过期日期',
      dataIndex: 'expiry_date',
      key: 'expiry_date',
      width: 130,
      render: (date: string | undefined) => {
        if (!date) return '—';
        const daysLeft = dayjs(date).diff(dayjs(), 'day');
        if (daysLeft < 0) return <Tag color="red">已过期</Tag>;
        if (daysLeft <= 30) return <Tag color="orange">{daysLeft}天后过期</Tag>;
        return <span>{date}</span>;
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <StatusTag status={status} colorMap={DRUG_STATUS_COLOR} />
      ),
    },
    {
      title: '操作',
      key: 'action',
      fixed: 'right' as const,
      width: 160,
      render: (_val: unknown, record: Medicine) => (
        <Space>
          <Button
            type="link"
            icon={<EditOutlined />}
            onClick={() => handleEdit(record)}
          >
            编辑
          </Button>
          <Popconfirm
            title="确定删除该药品吗？"
            onConfirm={() => handleDelete(record.id)}
            okText="确定"
            cancelText="取消"
          >
            <Button type="link" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 16,
        }}
      >
        <Title level={3} style={{ margin: 0 }}>
          药箱管理
        </Title>
        <Space>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/bmp"
            style={{ display: 'none' }}
            onChange={handleFileSelect}
          />
          <Button
            icon={<CameraOutlined />}
            onClick={handlePhotoAdd}
            loading={ocrLoading}
          >
            拍照添加
          </Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={handleAdd}>
            添加
          </Button>
        </Space>
      </div>
      {loading ? (
        <Skeleton active />
      ) : loadError ? (
        <Alert
          type="error"
          showIcon
          message="药品加载失败，请检查网络"
          action={
            <Button icon={<ReloadOutlined />} onClick={() => loadMedicines(1)}>
              重试
            </Button>
          }
        />
      ) : medicines.length === 0 ? (
        <Empty description="暂无药品，点击添加" />
      ) : isMobile ? (
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          {medicines.map((med) => {
            const daysLeft = med.expiry_date
              ? dayjs(med.expiry_date).diff(dayjs(), 'day')
              : null;
            return (
              <Card key={med.id} size="small" style={{ borderRadius: 8 }}>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                    marginBottom: 8,
                  }}
                >
                  <div>
                    <Typography.Text strong style={{ fontSize: 18 }}>
                      {med.name}
                    </Typography.Text>
                    {med.type && (
                      <Tag
                        color="blue"
                        style={{ marginLeft: 8, fontSize: 14 }}
                      >
                        {med.type}
                      </Tag>
                    )}
                  </div>
                  {med.status && (
                    <StatusTag status={med.status} colorMap={DRUG_STATUS_COLOR} />
                  )}
                </div>
                <div style={{ fontSize: 15, color: '#666', marginBottom: 12 }}>
                  <span style={{ marginRight: 16 }}>
                    数量：
                    {med.quantity == null ? (
                      '—'
                    ) : (
                      <Tag color={med.quantity <= 5 ? 'orange' : 'green'}>
                        {med.quantity <= 5 ? `低库存 ${med.quantity}` : med.quantity}
                      </Tag>
                    )}
                  </span>
                  {med.expiry_date && (
                    <span>
                      过期：
                      {daysLeft! < 0 ? (
                        <Tag color="red">已过期</Tag>
                      ) : daysLeft! <= 30 ? (
                        <Tag color="orange">{daysLeft}天后</Tag>
                      ) : (
                        <span>{med.expiry_date}</span>
                      )}
                    </span>
                  )}
                </div>
                <Space size="middle">
                  <Button
                    icon={<EditOutlined />}
                    onClick={() => handleEdit(med)}
                    style={{ minHeight: 44 }}
                  >
                    编辑
                  </Button>
                  <Popconfirm
                    title="确定删除该药品吗？"
                    onConfirm={() => handleDelete(med.id)}
                    okText="确定"
                    cancelText="取消"
                  >
                    <Button
                      danger
                      icon={<DeleteOutlined />}
                      style={{ minHeight: 44 }}
                    >
                      删除
                    </Button>
                  </Popconfirm>
                </Space>
              </Card>
            );
          })}
        </Space>
      ) : (
        <Table
          dataSource={medicines}
          columns={columns}
          rowKey="id"
          size="middle"
          scroll={{ x: 'max-content' }}
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: pagination.total,
            showSizeChanger: false,
          }}
          onChange={(pag) => loadMedicines(pag.current)}
        />
      )}
      <Drawer
        title={editingMedicine ? '编辑药品' : '添加药品'}
        width={isMobile ? '100%' : 480}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        destroyOnClose
        maskClosable={false}
        extra={
          <Button type="primary" onClick={handleSubmit}>
            提交
          </Button>
        }
        footer={
          <Space style={{ display: 'flex', justifyContent: 'flex-end' }}>
            <Button icon={<CloseOutlined />} onClick={() => setDrawerOpen(false)} style={{ minHeight: 48 }}>取消</Button>
            <Button type="primary" icon={<CheckCircleOutlined />} onClick={handleSubmit} style={{ minHeight: 48 }}>保存</Button>
          </Space>
        }
      >
        {ocrLoading && (
          <div style={{ textAlign: 'center', padding: '40px 0' }}>
            <Spin tip="正在识别药品信息..." />
          </div>
        )}
        {!ocrLoading && lowConfidenceFields.size > 0 && (
          <Alert
            type="warning"
            message="以下字段识别置信度较低，请核实标黄字段"
            showIcon
            style={{ marginBottom: 16 }}
          />
        )}
        <Form form={form} layout="vertical">
          <Form.Item
            label="药品名称"
            name="name"
            rules={[{ required: true, message: '请输入药品名称' }]}
          >
            <Input
              style={
                lowConfidenceFields.has('name')
                  ? { backgroundColor: '#fffbe6', borderColor: '#ffe58f' }
                  : undefined
              }
            />
          </Form.Item>
          <Form.Item
            label="类型"
            name="type"
            rules={[{ required: true, message: '请选择类型' }]}
          >
            <Select
              options={MEDICINE_TYPES.map((t) => ({ label: t, value: t }))}
              placeholder="请选择类型"
            />
          </Form.Item>
          <Alert
            type="info"
            showIcon
            message={editingMedicine?.properties?.drugClass
              ? `已保存的安全分类：${String(editingMedicine.properties.drugClass)}（来源：当前药品记录）`
              : '药理分类建议：未配置，需人工确认'}
            description={editingMedicine?.properties?.drugClass
              ? '该值来自当前记录，不代表系统已独立验证。请按说明书或药师意见复核。'
              : '药品名称和药箱类型不足以可靠推断 ACEI、抗凝药等药理分类。建议值：无；来源：没有经核验的成分/药理映射；置信度：无，因此不自动写入 drugClass。请依据说明书或药师核实后再维护。'}
            style={{ marginBottom: 16 }}
          />
          <Form.Item label="条形码" extra="可手动输入或相机扫码；校验通过后随药品信息保存">
            <Space.Compact style={{ width: '100%' }}>
              <Form.Item name="barcode" noStyle>
                <Input />
              </Form.Item>
              <Button
                icon={<CameraOutlined />}
                onClick={() => {
                  setScannerMessage('');
                  setScannerOpen(true);
                }}
                style={{ minHeight: 44 }}
                aria-label="相机扫码"
              >相机扫码</Button>
              <Button onClick={() => handleBarcodeCheck(form.getFieldValue('barcode') ?? '')} style={{ minHeight: 44 }}>校验</Button>
            </Space.Compact>
          </Form.Item>
          <Form.Item label="状态" name="status">
            <Select
              allowClear
              options={MEDICINE_STATUS.map((s) => ({ label: s, value: s }))}
              placeholder="请选择状态"
            />
          </Form.Item>
          <Form.Item label="用量" name="dosage">
            <Input
              placeholder="如：每次1片，每日3次"
              style={
                lowConfidenceFields.has('dosage')
                  ? { backgroundColor: '#fffbe6', borderColor: '#ffe58f' }
                  : undefined
              }
            />
          </Form.Item>
          <Form.Item label="库存数量" name="quantity">
            <InputNumber min={0} placeholder="如：30" style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="过期日期" name="expiry_date">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="备注" name="notes">
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Drawer>
      <Modal
        title="扫描药品条形码"
        open={scannerOpen}
        onCancel={closeBarcodeScanner}
        footer={<Button onClick={closeBarcodeScanner} style={{ minHeight: 44 }}>关闭相机并返回</Button>}
        destroyOnClose
        maskClosable={false}
      >
        <video
          ref={videoRef}
          muted
          playsInline
          aria-label="药品条形码相机取景"
          style={{ width: '100%', minHeight: 180, maxHeight: 320, objectFit: 'cover', background: '#111' }}
        />
        <Typography.Paragraph aria-live="polite" style={{ marginTop: 12, marginBottom: 0, fontSize: 16 }}>
          {scannerStarting ? '正在启动相机…' : scannerMessage || '请将 EAN-8 或 EAN-13 条形码对准相机。也可以关闭后手动输入。'}
        </Typography.Paragraph>
      </Modal>
    </div>
  );
}
