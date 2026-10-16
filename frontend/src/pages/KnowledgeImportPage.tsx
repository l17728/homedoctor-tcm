import { useState, useEffect, useCallback } from 'react';
import {
  Upload,
  Button,
  Table,
  Popconfirm,
  message,
  Empty,
  Skeleton,
  Typography,
  Space,
  Tag,
  Card,
  Progress,
  Modal,
} from 'antd';
import type { UploadProps } from 'antd';
import {
  InboxOutlined,
  DeleteOutlined,
  FileTextOutlined,
  EyeOutlined,
  CloudUploadOutlined,
} from '@ant-design/icons';
import {
  uploadKnowledgeFile,
  getRecentImports,
  deleteImport,
  detectFileType,
  parseSummary,
  getWordCount,
  FILE_TYPE_LABEL,
  FILE_TYPE_COLOR,
  type KnowledgeImportEntry,
  type UploadResponse,
} from '../api/knowledgeImportApi';

const { Dragger } = Upload;
const { Title, Text, Paragraph } = Typography;

const ACCEPTED_EXT = '.pdf,.docx,.doc,.txt,.md,.jpg,.jpeg,.png,.webp';
const MAX_SIZE_MB = 20;

export default function KnowledgeImportPage() {
  const [recent, setRecent] = useState<KnowledgeImportEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [lastUpload, setLastUpload] = useState<UploadResponse | null>(null);
  const [previewEntry, setPreviewEntry] = useState<KnowledgeImportEntry | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const { items } = await getRecentImports(50);
      setRecent(items);
    } catch {
      // handled
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleUpload = async (file: File) => {
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      message.error(`文件过大，上限 ${MAX_SIZE_MB}MB`);
      return false;
    }
    setUploading(true);
    setProgress(10);
    try {
      setProgress(40);
      const res = await uploadKnowledgeFile(file);
      setProgress(100);
      setLastUpload(res);
      message.success(`「${res.title}」导入成功，识别 ${res.word_count} 字`);
      loadData();
    } catch (err) {
      const msg = err instanceof Error ? err.message : '导入失败';
      message.error(msg);
    } finally {
      setTimeout(() => {
        setProgress(0);
        setUploading(false);
      }, 800);
    }
    return false;
  };

  const draggerProps: UploadProps = {
    name: 'file',
    multiple: false,
    accept: ACCEPTED_EXT,
    showUploadList: false,
    beforeUpload: (file) => {
      handleUpload(file);
      return false;
    },
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteImport(id);
      message.success('已删除');
      setRecent((prev) => prev.filter((e) => e.id !== id));
    } catch {
      message.error('删除失败');
    }
  };

  const openPreview = (entry: KnowledgeImportEntry) => {
    setPreviewEntry(entry);
    setPreviewOpen(true);
  };

  const columns = [
    {
      title: '文件名',
      dataIndex: 'source_url',
      key: 'source_url',
      ellipsis: true,
      render: (filename: string | null, r: KnowledgeImportEntry) => (
        <Space>
          <FileTextOutlined />
          <Button type="link" onClick={() => openPreview(r)} style={{ padding: 0 }}>
            {filename || r.title}
          </Button>
        </Space>
      ),
    },
    {
      title: '类型',
      key: 'type',
      width: 90,
      render: (_: unknown, r: KnowledgeImportEntry) => {
        const fileType = detectFileType(r.source_url ?? r.title);
        return (
          <Tag color={FILE_TYPE_COLOR[fileType]}>
            {FILE_TYPE_LABEL[fileType]}
          </Tag>
        );
      },
    },
    {
      title: '字数',
      key: 'word_count',
      width: 100,
      render: (_: unknown, r: KnowledgeImportEntry) => {
        const wc = getWordCount(r);
        return wc > 0 ? wc.toLocaleString() : '—';
      },
    },
    {
      title: '识别标签',
      dataIndex: 'tags',
      key: 'tags',
      render: (tags: string[]) =>
        tags.length > 0 ? (
          <Space size={[2, 2]} wrap>
            {tags.slice(0, 6).map((t) => (
              <Tag key={t} color="green" style={{ margin: 0 }}>
                {t}
              </Tag>
            ))}
            {tags.length > 6 && <Tag>+{tags.length - 6}</Tag>}
          </Space>
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
    {
      title: '导入时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 170,
      render: (t: string) => t || '—',
    },
    {
      title: '操作',
      key: 'action',
      fixed: 'right' as const,
      width: 140,
      render: (_: unknown, r: KnowledgeImportEntry) => (
        <Space size={0}>
          <Button
            type="link"
            icon={<EyeOutlined />}
            onClick={() => openPreview(r)}
          >
            预览
          </Button>
          <Popconfirm
            title="确定删除该导入记录吗？"
            onConfirm={() => handleDelete(r.id)}
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
          <CloudUploadOutlined style={{ marginRight: 8 }} />
          知识导入
        </Title>
      </div>

      <Card style={{ marginBottom: 16 }}>
        <Dragger {...draggerProps} disabled={uploading}>
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">
            点击或拖拽文件到此处导入知识库
          </p>
          <p className="ant-upload-hint">
            支持 PDF / Word / TXT / Markdown / 图片（JPG/PNG/WEBP），单文件上限 {MAX_SIZE_MB}MB
          </p>
        </Dragger>

        {uploading && (
          <div style={{ marginTop: 12 }}>
            <Progress percent={progress} status={progress === 100 ? 'success' : 'active'} />
          </div>
        )}

        <Space style={{ marginTop: 12 }} wrap>
          <Tag color="red">PDF</Tag>
          <Tag color="blue">Word</Tag>
          <Tag>TXT / Markdown</Tag>
          <Tag color="purple">图片 (OCR)</Tag>
        </Space>
      </Card>

      {lastUpload && (
        <Card
          title="最近导入结果"
          size="small"
          style={{ marginBottom: 16 }}
          extra={
            <Button type="link" onClick={() => setLastUpload(null)}>
              收起
            </Button>
          }
        >
          <Space direction="vertical" style={{ width: '100%' }} size="small">
            <div>
              <Text strong>{lastUpload.title}</Text>
              <Tag
                color={FILE_TYPE_COLOR[detectFileType(lastUpload.source_url ?? '')]}
                style={{ marginLeft: 8 }}
              >
                {FILE_TYPE_LABEL[detectFileType(lastUpload.source_url ?? '')]}
              </Tag>
            </div>
            <Space>
              <Tag color="blue">{lastUpload.word_count.toLocaleString()} 字</Tag>
              <Tag color="cyan">{lastUpload.sections_parsed} 段落</Tag>
            </Space>
            {lastUpload.tags.length > 0 && (
              <div>
                <Text type="secondary" style={{ marginRight: 8 }}>
                  识别到：
                </Text>
                <Space size={[4, 4]} wrap>
                  {lastUpload.tags.map((t) => (
                    <Tag key={t} color="green">
                      {t}
                    </Tag>
                  ))}
                </Space>
              </div>
            )}
          </Space>
        </Card>
      )}

      {loading ? (
        <Skeleton active />
      ) : recent.length === 0 ? (
        <Empty description="暂无导入记录，上传文件开始构建知识库" />
      ) : (
        <Table
          dataSource={recent}
          columns={columns}
          rowKey="id"
          size="middle"
          pagination={{ pageSize: 20, showSizeChanger: false }}
        />
      )}

      <Modal
        title={previewEntry?.title ?? '内容预览'}
        open={previewOpen}
        onCancel={() => setPreviewOpen(false)}
        footer={null}
        width={640}
        destroyOnClose
      >
        {previewEntry && (
          <PreviewContent entry={previewEntry} />
        )}
      </Modal>
    </div>
  );
}

function PreviewContent({ entry }: { entry: KnowledgeImportEntry }) {
  const summary = parseSummary(entry.summary);
  const wc = getWordCount(entry);
  const fileType = detectFileType(entry.source_url ?? entry.title);

  return (
    <Space direction="vertical" style={{ width: '100%' }} size="small">
      <Space wrap>
        <Tag color={FILE_TYPE_COLOR[fileType]}>{FILE_TYPE_LABEL[fileType]}</Tag>
        <Tag color="blue">{wc.toLocaleString()} 字</Tag>
        {summary?.metadata.sections ? (
          <Tag color="cyan">{summary.metadata.sections} 段落</Tag>
        ) : null}
        {entry.source_url && (
          <Text type="secondary" style={{ fontSize: 14 }}>
            {entry.source_url}
          </Text>
        )}
      </Space>

      {entry.tags.length > 0 && (
        <div>
          <Text type="secondary" style={{ marginRight: 8 }}>
            识别标签：
          </Text>
          <Space size={[4, 4]} wrap>
            {entry.tags.map((t) => (
              <Tag key={t} color="green">
                {t}
              </Tag>
            ))}
          </Space>
        </div>
      )}

      <Paragraph
        ellipsis={{ rows: 12, expandable: true, symbol: '展开全部' }}
        style={{
          marginTop: 8,
          whiteSpace: 'pre-wrap',
          maxHeight: 400,
          overflowY: 'auto',
          background: '#fafafa',
          padding: 12,
          borderRadius: 6,
        }}
      >
        {entry.content || '（无文本内容）'}
      </Paragraph>
    </Space>
  );
}
