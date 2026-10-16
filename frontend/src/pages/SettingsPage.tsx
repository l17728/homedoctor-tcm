import { useState, useEffect, useCallback } from 'react';
import {
  Card,
  Form,
  Switch,
  Typography,
  Divider,
  Modal,
  Space,
  Button,
  Table,
  Tag,
  Alert,
  message,
  Input,
} from 'antd';
import type { TableColumnsType } from 'antd';
import {
  ExclamationCircleOutlined,
  SaveOutlined,
  DownloadOutlined,
  DeleteOutlined,
  CloudUploadOutlined,
  EyeOutlined,
  LogoutOutlined,
} from '@ant-design/icons';
import { useTheme } from '../hooks/useTheme';
import { useElderlyMode } from '../contexts/ElderlyModeContext';
import { request } from '../api/client';
import { APP_VERSION } from '../constants';
import PushNotificationSettings from '../components/PushNotificationSettings';
import { useAuth } from '../hooks/useAuth';
import { useNavigate } from 'react-router-dom';

const { Title, Text, Paragraph } = Typography;

// ---------------------------------------------------------------------------
// Types — mirror backend response shapes (backup.py, account.py, export.py)
// ---------------------------------------------------------------------------

interface BackupItem {
  filename: string;
  size: number;
  encrypted: boolean;
  created_at: string;
}

interface BackupListResponse {
  backups: BackupItem[];
}

interface BackupCreateResponse {
  success: boolean;
  filename: string;
  size_bytes: number;
  encrypted: boolean;
  created_at: string;
}

interface BackupRestoreResponse {
  success: boolean;
  message: string;
  filename: string;
}

interface PreviewResponse {
  user_id: string;
  username: string;
  data_counts: Record<string, number>;
  total_records: number;
}

interface DeleteResponse {
  deleted: boolean;
  timestamp: string;
  message: string;
}

interface ExportData {
  export_date: string;
  user: {
    id: string;
    username: string | null;
    family_id: string;
  };
  data: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Chinese label mapping for account preview data counts
// ---------------------------------------------------------------------------

const DATA_COUNT_LABELS: Record<string, string> = {
  conversations: '对话记录',
  knowledge_entries: '知识条目',
  favorites: '收藏',
  constitution_assessments: '体质评估',
  user_profiles: '健康档案',
  reminders: '提醒',
  family_members: '家庭成员',
  medicines: '药品',
  medication_logs: '服药记录',
  audit_log: '审计日志',
};

// ---------------------------------------------------------------------------
// Format helpers
// ---------------------------------------------------------------------------

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleString('zh-CN');
}

// ===========================================================================
// Component
// ===========================================================================

export default function SettingsPage() {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const { isDark, toggleTheme } = useTheme();
  const { isElderlyMode, setElderly } = useElderlyMode();

  // Backup state
  const [backupList, setBackupList] = useState<BackupItem[]>([]);
  const [backupListLoading, setBackupListLoading] = useState(true);
  const [backupListError, setBackupListError] = useState(false);
  const [backupLoading, setBackupLoading] = useState(false);
  const [restoreLoading, setRestoreLoading] = useState<string | null>(null);

  // Export state
  const [exportLoading, setExportLoading] = useState(false);

  // Account preview state
  const [previewData, setPreviewData] = useState<PreviewResponse | null>(null);
  const [previewModalOpen, setPreviewModalOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);

  // Delete account state
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState('');
  const [deleteLoading, setDeleteLoading] = useState(false);

  // -----------------------------------------------------------------------
  // Load backup list on mount
  // -----------------------------------------------------------------------

  const loadBackupList = useCallback(async () => {
    setBackupListLoading(true);
    setBackupListError(false);
    try {
      const res = await request<BackupListResponse>('/api/backup/list');
      setBackupList(res.backups);
    } catch {
      setBackupListError(true);
    } finally {
      setBackupListLoading(false);
    }
  }, []);

  useEffect(() => {
    loadBackupList();
  }, [loadBackupList]);

  // -----------------------------------------------------------------------
  // Existing: elderly mode toggle confirmation
  // -----------------------------------------------------------------------

  const handleElderlyToggle = (checked: boolean) => {
    if (checked) {
      Modal.confirm({
        title: '切换到长辈模式',
        icon: <ExclamationCircleOutlined />,
        content: '将切换到简化界面（3个功能标签、大字体），适合长辈使用。确定要切换吗？',
        okText: '确定切换',
        cancelText: '取消',
        onOk: () => setElderly(true),
      });
    } else {
      setElderly(false);
    }
  };

  // -----------------------------------------------------------------------
  // Backup: create + restore
  // -----------------------------------------------------------------------

  const handleCreateBackup = async () => {
    setBackupLoading(true);
    try {
      await request<BackupCreateResponse>('/api/backup', { method: 'POST' });
      message.success('备份创建成功');
      await loadBackupList();
    } catch {
      message.error('备份失败');
    } finally {
      setBackupLoading(false);
    }
  };

  const handleRestore = (filename: string) => {
    Modal.confirm({
      title: '恢复备份',
      icon: <ExclamationCircleOutlined />,
      content: '恢复后需要重启服务才能生效，确定要恢复吗？',
      okText: '确定恢复',
      cancelText: '取消',
      onOk: async () => {
        setRestoreLoading(filename);
        try {
          await request<BackupRestoreResponse>('/api/backup/restore', {
            method: 'POST',
            body: JSON.stringify({ filename }),
          });
          message.success('备份已暂存，重启服务后生效');
          Modal.info({
            title: '恢复已就绪',
            content: '备份文件已解密并暂存，请重启服务以完成恢复操作。',
          });
        } catch {
          message.error('恢复失败');
        } finally {
          setRestoreLoading(null);
        }
      },
    });
  };

  // -----------------------------------------------------------------------
  // Data export — download JSON blob
  // -----------------------------------------------------------------------

  const handleExport = async () => {
    setExportLoading(true);
    try {
      const data = await request<ExportData>('/api/export');
      const json = JSON.stringify(data, null, 2);
      const blob = new Blob([json], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `homedoctor-export-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      message.success('数据导出成功');
    } catch {
      message.error('导出失败');
    } finally {
      setExportLoading(false);
    }
  };

  // -----------------------------------------------------------------------
  // Account preview
  // -----------------------------------------------------------------------

  const handlePreview = async () => {
    setPreviewLoading(true);
    try {
      const data = await request<PreviewResponse>('/api/account/preview');
      setPreviewData(data);
      setPreviewModalOpen(true);
    } catch {
      message.error('获取数据概况失败');
    } finally {
      setPreviewLoading(false);
    }
  };

  // -----------------------------------------------------------------------
  // Account deletion — double confirmation + type-to-confirm (PIPL §47)
  // -----------------------------------------------------------------------

  const handleDeleteClick = () => {
    Modal.confirm({
      title: '确认删除账户',
      icon: <ExclamationCircleOutlined />,
      content: '确定要删除账户吗？所有数据将被永久删除，此操作不可撤销。',
      okText: '继续',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: () => {
        setDeleteConfirmText('');
        setDeleteModalOpen(true);
      },
    });
  };

  const handleDeleteConfirm = async () => {
    if (deleteConfirmText !== '删除') {
      message.warning('请输入"删除"以确认');
      return;
    }
    setDeleteLoading(true);
    try {
      await request<DeleteResponse>('/api/account', { method: 'DELETE' });
      message.success('账户已删除');
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      localStorage.removeItem('current_member_id');
      setDeleteModalOpen(false);
      window.location.href = '/login';
    } catch {
      message.error('删除账户失败');
    } finally {
      setDeleteLoading(false);
    }
  };

  // -----------------------------------------------------------------------
  // Backup table columns
  // -----------------------------------------------------------------------

  const backupColumns: TableColumnsType<BackupItem> = [
    {
      title: '文件名',
      dataIndex: 'filename',
      key: 'filename',
      ellipsis: true,
    },
    {
      title: '大小',
      dataIndex: 'size',
      key: 'size',
      width: 100,
      render: (value: number) => formatFileSize(value),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 200,
      render: (value: string) => formatDate(value),
    },
    {
      title: '加密',
      dataIndex: 'encrypted',
      key: 'encrypted',
      width: 90,
      render: (value: boolean) =>
        value ? <Tag color="green">已加密</Tag> : <Tag>未加密</Tag>,
    },
    {
      title: '操作',
      key: 'action',
      width: 100,
      render: (_, record) => (
        <Button
          type="link"
          icon={<CloudUploadOutlined />}
          loading={restoreLoading === record.filename}
          onClick={() => handleRestore(record.filename)}
        >
          恢复
        </Button>
      ),
    },
  ];

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  return (
    <div>
      <Title level={3}>设置</Title>

      {/* 1. 显示设置 (existing — dark mode + elderly mode) */}
      <Card title="显示设置">
        <Form layout="vertical">
          <Form.Item label="深色模式">
            <Switch checked={isDark} onChange={toggleTheme} />
          </Form.Item>
          <Divider />
          <Form.Item
            label={
              <Space>
                <Text strong>长辈模式</Text>
                <Text type="secondary">简化界面 · 大字体 · 3个功能</Text>
              </Space>
            }
          >
            <Switch checked={isElderlyMode} onChange={handleElderlyToggle} />
          </Form.Item>
        </Form>
      </Card>

      <Divider />
      <Card title="浏览器推送">
        <PushNotificationSettings />
      </Card>

      <Divider />

      {/* 2. 数据备份 — 长辈模式隐藏 */}
      {!isElderlyMode && (
        <>
          <Card
            title="数据备份"
            extra={
              <Button
                type="primary"
                icon={<SaveOutlined />}
                loading={backupLoading}
                onClick={handleCreateBackup}
              >
                创建备份
              </Button>
            }
          >
            {backupListError ? (
              <Alert
                type="error"
                showIcon
                message="备份列表加载失败"
                description="请检查网络或当前账户权限后重试。"
                action={<Button onClick={() => void loadBackupList()} style={{ minHeight: 44 }}>重试</Button>}
              />
            ) : (
              <Table<BackupItem>
                columns={backupColumns}
                dataSource={backupList}
                rowKey="filename"
                pagination={false}
                loading={backupListLoading}
                size="middle"
                scroll={{ x: 'max-content' }}
                locale={{ emptyText: '暂无备份，点击上方按钮创建' }}
              />
            )}
          </Card>

          <Divider />

          {/* 3. 数据导出 — 长辈模式隐藏 */}
          <Card title="数据导出">
            <Paragraph type="secondary">
              导出您的所有健康数据（药品、提醒、体质评估、健康档案等）为 JSON 文件
            </Paragraph>
            <Button
              type="primary"
              icon={<DownloadOutlined />}
              loading={exportLoading}
              onClick={handleExport}
            >
              导出数据
            </Button>
          </Card>
        </>
      )}

      <Divider />

      {/* 4. 关于 (existing — version updated to 0.4.0) */}
      <Card title="关于">
        <p>家庭医生 · 您的养生助手</p>
        <p>版本：{APP_VERSION}</p>
        <Button
          icon={<LogoutOutlined />}
          style={{ minHeight: 44, marginTop: 8 }}
          onClick={async () => {
            await logout();
            navigate('/login', { replace: true });
          }}
        >
          退出登录
        </Button>
      </Card>

      {/* 5. 账户管理 — 长辈模式隐藏（危险操作不暴露给长辈） */}
      {!isElderlyMode && (
        <>
          <Divider />
          <Card title="账户管理">
            <Alert
              type="warning"
              message="以下操作不可撤销，请谨慎操作"
              showIcon
              style={{ marginBottom: 16 }}
            />
            <Space>
              <Button
                icon={<EyeOutlined />}
                loading={previewLoading}
                onClick={handlePreview}
              >
                查看数据概况
              </Button>
              <Button danger icon={<DeleteOutlined />} onClick={handleDeleteClick}>
                删除账户
              </Button>
            </Space>
          </Card>
        </>
      )}

      {/* Preview data modal */}
      <Modal
        title="账户数据概况"
        open={previewModalOpen}
        onCancel={() => setPreviewModalOpen(false)}
        footer={[
          <Button key="close" onClick={() => setPreviewModalOpen(false)}>
            关闭
          </Button>,
        ]}
      >
        {previewData && (
          <div>
            <Paragraph>
              您的账户包含以下数据（共 {previewData.total_records} 条记录）：
            </Paragraph>
            <ul style={{ paddingLeft: 20 }}>
              {Object.entries(previewData.data_counts).map(([key, count]) => (
                <li key={key}>
                  <Text>{DATA_COUNT_LABELS[key] ?? key}</Text>
                  <Text strong>：{count}</Text>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Modal>

      {/* Delete confirmation modal — type-to-confirm pattern */}
      <Modal
        title="永久删除账户"
        open={deleteModalOpen}
        confirmLoading={deleteLoading}
        okText="确认删除"
        cancelText="取消"
        okButtonProps={{ danger: true }}
        onCancel={() => setDeleteModalOpen(false)}
        onOk={handleDeleteConfirm}
      >
        <Alert
          type="error"
          message="此操作将永久删除您的账户及所有关联数据，且不可恢复。"
          showIcon
          style={{ marginBottom: 16 }}
        />
        <Paragraph>
          请输入 <Text strong code>删除</Text> 以确认：
        </Paragraph>
        <Input
          value={deleteConfirmText}
          onChange={(e) => setDeleteConfirmText(e.target.value)}
          placeholder={'请输入 "删除" 以确认'}
        />
      </Modal>
    </div>
  );
}
