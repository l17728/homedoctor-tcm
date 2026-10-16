import { useState, useEffect, useCallback } from 'react';
import {
  Card,
  Row,
  Col,
  Button,
  Tag,
  Typography,
  Skeleton,
  Empty,
  Space,
  Statistic,
  Progress,
  List,
  Modal,
  Input,
  InputNumber,
  Switch,
  Form,
  Avatar,
  Alert,
  Divider,
  message,
} from 'antd';
import {
  TeamOutlined,
  UserOutlined,
  EyeOutlined,
  SettingOutlined,
  UserAddOutlined,
  HeartOutlined,
  MedicineBoxOutlined,
  WarningOutlined,
  BellOutlined,
  CalendarOutlined,
  SafetyOutlined,
  ReloadOutlined,
  CheckCircleOutlined,
  MessageOutlined,
  AlertOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import {
  getSharedWithMe,
  getHealthSummary,
  getWeeklyReport,
  setAlertConfig,
  inviteFamilyMember,
  getMissedAlerts,
  type SharedUser,
  type HealthSummary,
  type WeeklyReport,
  type AlertConfig,
  type MissedAlertsResponse,
} from '../api/remoteAssistApi';

const { Title, Text, Paragraph } = Typography;

const ROLE_COLOR: Record<string, string> = {
  管理员: 'gold',
  长辈: 'blue',
  家属查看: 'green',
};

const SEVERITY_COLOR: Record<string, string> = {
  critical: 'red',
  warning: 'orange',
};

function adherenceColor(rate: number): string {
  if (rate >= 80) return '#52c41a';
  if (rate >= 60) return '#faad14';
  return '#ff4d4f';
}

function avatarColor(name: string): string {
  const colors = ['#1890ff', '#52c41a', '#722ed1', '#fa8c16', '#eb2f96', '#13c2c2'];
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return colors[Math.abs(hash) % colors.length] ?? '#1890ff';
}

// ===========================================================================
// Main Page
// ===========================================================================

export default function RemoteAssistPage() {
  const [sharedUsers, setSharedUsers] = useState<SharedUser[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [selectedUser, setSelectedUser] = useState<SharedUser | null>(null);
  const [summary, setSummary] = useState<HealthSummary | null>(null);
  const [weekly, setWeekly] = useState<WeeklyReport | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [alertModalOpen, setAlertModalOpen] = useState(false);
  const [inviteModalOpen, setInviteModalOpen] = useState(false);
  const [alertForm] = Form.useForm<AlertConfig & { expired_medicine_alert: boolean }>();
  const [inviteForm] = Form.useForm<{ username: string }>();
  const [savingAlert, setSavingAlert] = useState(false);
  const [inviting, setInviting] = useState(false);
  const [missedAlerts, setMissedAlerts] = useState<MissedAlertsResponse | null>(null);

  const fetchShared = useCallback(async () => {
    setLoadingList(true);
    try {
      const users = await getSharedWithMe();
      setSharedUsers(users);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '加载共享列表失败';
      message.error(msg);
    } finally {
      setLoadingList(false);
    }
  }, []);

  useEffect(() => {
    fetchShared();
  }, [fetchShared]);

  const handleViewSummary = useCallback(async (user: SharedUser) => {
    setSelectedUser(user);
    setLoadingDetail(true);
    setSummary(null);
    setWeekly(null);
    setMissedAlerts(null);
    try {
      const [s, w, ma] = await Promise.all([
        getHealthSummary(user.sharer_id),
        getWeeklyReport(user.sharer_id),
        getMissedAlerts(user.sharer_id).catch(() => null),
      ]);
      setSummary(s);
      setWeekly(w);
      setMissedAlerts(ma);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '加载健康摘要失败';
      message.error(msg);
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  const openAlertModal = () => {
    const cfg = (selectedUser?.alert_config ?? {}) as AlertConfig;
    alertForm.setFieldsValue({
      missed_reminder_threshold: cfg.missed_reminder_threshold,
      expired_medicine_alert: cfg.expired_medicine_alert,
      low_stock_threshold: cfg.low_stock_threshold,
    });
    setAlertModalOpen(true);
  };

  const handleSaveAlert = async () => {
    if (!selectedUser) return;
    try {
      const values = await alertForm.validateFields();
      setSavingAlert(true);
      const config: AlertConfig = {
        missed_reminder_threshold: values.missed_reminder_threshold ?? undefined,
        expired_medicine_alert: values.expired_medicine_alert,
        low_stock_threshold: values.low_stock_threshold ?? undefined,
      };
      await setAlertConfig(selectedUser.sharer_id, config);
      message.success('预警阈值已保存');
      setAlertModalOpen(false);
      // refresh local list state to reflect new config
      setSharedUsers((prev) =>
        prev.map((u) =>
          u.share_id === selectedUser.share_id
            ? { ...u, alert_config: { ...u.alert_config, ...config } }
            : u,
        ),
      );
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    } finally {
      setSavingAlert(false);
    }
  };

  const handleInvite = async () => {
    try {
      const values = await inviteForm.validateFields();
      setInviting(true);
      await inviteFamilyMember(values.username);
      message.success(`已邀请 ${values.username}`);
      inviteForm.resetFields();
      setInviteModalOpen(false);
      fetchShared();
    } catch (err) {
      if (err instanceof Error) message.error(err.message);
    } finally {
      setInviting(false);
    }
  };

  return (
    <div>
      <Row justify="space-between" align="middle" style={{ marginBottom: 16 }} gutter={[16, 16]}>
        <Col>
          <Title level={3} style={{ marginBottom: 0 }}>
            <TeamOutlined style={{ marginRight: 8, color: '#1890ff' }} />
            远程协助
          </Title>
        </Col>
        <Col>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={fetchShared} loading={loadingList}>
              刷新
            </Button>
            <Button
              type="primary"
              icon={<UserAddOutlined />}
              onClick={() => setInviteModalOpen(true)}
            >
              邀请家属
            </Button>
          </Space>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        {/* Section 1 — 我的家人列表 */}
        <Col xs={24} lg={8}>
          <Card
            title={
              <Space>
                <TeamOutlined style={{ color: '#1890ff' }} />
                <span>我的家人</span>
                {sharedUsers.length > 0 && <Tag color="blue">{sharedUsers.length}</Tag>}
              </Space>
            }
            style={{ height: '100%' }}
          >
            {loadingList ? (
              <Skeleton active paragraph={{ rows: 4 }} />
            ) : sharedUsers.length === 0 ? (
              <Empty description="暂无共享家人，点击「邀请家属」" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ) : (
              <List
                dataSource={sharedUsers}
                renderItem={(user) => {
                  const isSelected = selectedUser?.share_id === user.share_id;
                  return (
                    <List.Item style={{ padding: '8px 0', borderBottom: '1px solid #f0f0f0' }}>
                      <Card
                        size="small"
                        hoverable
                        onClick={() => handleViewSummary(user)}
                        style={{
                          width: '100%',
                          borderLeft: `4px solid ${isSelected ? '#1890ff' : avatarColor(user.sharer_name)}`,
                          background: isSelected ? '#e6f7ff' : undefined,
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                          <Avatar
                            style={{ backgroundColor: avatarColor(user.sharer_name), flexShrink: 0 }}
                            icon={<UserOutlined />}
                            size={44}
                          >
                            {user.sharer_name.slice(0, 1)}
                          </Avatar>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <Text strong style={{ fontSize: 16 }}>{user.sharer_name}</Text>
                            <div style={{ marginTop: 4 }}>
                              <Tag color={ROLE_COLOR[user.role] ?? 'default'}>{user.role}</Tag>
                            </div>
                          </div>
                          <Button
                            type={isSelected ? 'primary' : 'default'}
                            icon={<EyeOutlined />}
                          >
                            查看摘要
                          </Button>
                        </div>
                      </Card>
                    </List.Item>
                  );
                }}
              />
            )}
          </Card>
        </Col>

        {/* Section 2 — 健康摘要 + 周报 */}
        <Col xs={24} lg={16}>
          {!selectedUser ? (
            <Card style={{ height: '100%' }}>
              <Empty
                description="从左侧选择家人查看健康摘要"
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            </Card>
          ) : loadingDetail ? (
            <Card>
              <Skeleton active paragraph={{ rows: 8 }} />
            </Card>
          ) : (
            <Space direction="vertical" size={16} style={{ width: '100%' }}>
              {/* 摘要卡片 */}
              <Card
                title={
                  <Space>
                    <HeartOutlined style={{ color: '#eb2f96' }} />
                    <span>{selectedUser.sharer_name} 的健康摘要</span>
                  </Space>
                }
                extra={
                  <Button icon={<SettingOutlined />} onClick={openAlertModal}>
                    设置提醒阈值
                  </Button>
                }
              >
                {summary ? (
                  <div>
                    <Row gutter={[16, 16]} align="middle">
                      <Col xs={24} sm={8} style={{ textAlign: 'center' }}>
                        <Progress
                          type="circle"
                          percent={Math.round(summary.medication_adherence.rate)}
                          strokeColor={adherenceColor(summary.medication_adherence.rate)}
                          width={110}
                          format={(p) => `${p}%`}
                        />
                        <div style={{ marginTop: 8, color: '#666' }}>用药依从率（7 天）</div>
                      </Col>
                      <Col xs={24} sm={16}>
                        <Row gutter={[12, 12]}>
                          <Col span={8}>
                            <Statistic
                              title="按时服药"
                              value={summary.medication_adherence.taken_7d}
                              prefix={<CheckCircleOutlined style={{ color: '#52c41a' }} />}
                              valueStyle={{ color: '#52c41a' }}
                            />
                          </Col>
                          <Col span={8}>
                            <Statistic
                              title="漏服次数"
                              value={summary.medication_adherence.missed_7d}
                              prefix={<WarningOutlined />}
                              valueStyle={{ color: '#ff4d4f' }}
                            />
                          </Col>
                          <Col span={8}>
                            <Statistic
                              title="今日漏服提醒"
                              value={summary.missed_reminders}
                              prefix={<BellOutlined />}
                              valueStyle={{ color: summary.missed_reminders > 0 ? '#faad14' : undefined }}
                            />
                          </Col>
                        </Row>
                        {summary.constitution_summary && (
                          <div style={{ marginTop: 12 }}>
                            <Text type="secondary">体质：</Text>
                            <Tag color="purple" style={{ marginLeft: 4 }}>
                              {summary.constitution_summary.primary_type}
                            </Tag>
                            {summary.constitution_summary.secondary_types.map((t) => (
                              <Tag key={t}>兼：{t}</Tag>
                            ))}
                          </div>
                        )}
                      </Col>
                    </Row>

                    {summary.recent_alerts.length > 0 && (
                      <div style={{ marginTop: 16 }}>
                        <Text strong>
                          <WarningOutlined style={{ color: '#fa541c', marginRight: 4 }} />
                          近期预警
                        </Text>
                        <div style={{ marginTop: 8 }}>
                          {summary.recent_alerts.map((alert, idx) => (
                            <Alert
                              key={idx}
                              type={alert.severity === 'critical' ? 'error' : 'warning'}
                              showIcon
                              message={
                                <Space wrap>
                                  <Tag color={SEVERITY_COLOR[alert.severity] ?? 'default'}>
                                    {alert.type}
                                  </Tag>
                                  <Text strong>{alert.name}</Text>
                                  <Text type="secondary">{alert.detail}</Text>
                                </Space>
                              }
                              style={{ marginBottom: 6 }}
                            />
                          ))}
                        </div>
                      </div>
                    )}
                    <Text type="secondary" style={{ fontSize: 14, display: 'block', marginTop: 8 }}>
                      生成时间：{summary.generated_at}
                    </Text>
                  </div>
                ) : (
                  <Empty description="暂无摘要数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                )}
              </Card>

              {missedAlerts && missedAlerts.total > 0 && (
                <Card
                  style={{
                    marginBottom: 0,
                    borderColor: missedAlerts.severity === 'critical' ? '#ff4d4f' : '#faad14',
                    borderWidth: 2,
                  }}
                  title={
                    <Space>
                      <AlertOutlined style={{ color: missedAlerts.severity === 'critical' ? '#ff4d4f' : '#faad14' }} />
                      <span>漏服告警</span>
                      <Tag color={missedAlerts.severity === 'critical' ? 'red' : 'orange'}>
                        近 {missedAlerts.window_hours}h 漏服 {missedAlerts.total} 次
                      </Tag>
                      {missedAlerts.severity === 'critical' && (
                        <Tag color="red" style={{ fontWeight: 600 }}>严重</Tag>
                      )}
                    </Space>
                  }
                >
                  <Space direction="vertical" style={{ width: '100%' }} size="small">
                    {missedAlerts.alerts.map((alert, idx) => (
                      <div
                        key={idx}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '8px 12px',
                          background: '#fff2f0',
                          borderRadius: 6,
                          flexWrap: 'wrap',
                          gap: 8,
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                          <Tag color="red" style={{ fontSize: 14 }}>
                            <ClockCircleOutlined /> {alert.missed_time}
                          </Tag>
                          <Text strong style={{ fontSize: 16 }}>{alert.medicine_name}</Text>
                        </div>
                        <Tag color="volcano">
                          {alert.hours_ago >= 1
                            ? `${Math.floor(alert.hours_ago)} 小时前`
                            : '刚刚'}
                        </Tag>
                      </div>
                    ))}
                  </Space>
                  {missedAlerts.severity === 'critical' && (
                    <Alert
                      type="error"
                      showIcon
                      message={`近 ${missedAlerts.window_hours} 小时内漏服超过 3 次，请关注 ${missedAlerts.sharer_name} 的用药情况`}
                      style={{ marginTop: 12 }}
                    />
                  )}
                  <Text type="secondary" style={{ fontSize: 14, display: 'block', marginTop: 8 }}>
                    检查时间：{missedAlerts.checked_at}
                  </Text>
                </Card>
              )}

              {/* 周报卡片 */}
              <Card
                title={
                  <Space>
                    <CalendarOutlined style={{ color: '#722ed1' }} />
                    <span>本周健康报告</span>
                    {weekly && (
                      <Text type="secondary" style={{ fontSize: 14 }}>
                        {weekly.period.from} ~ {weekly.period.to}
                      </Text>
                    )}
                  </Space>
                }
              >
                {weekly ? (
                  <div>
                    <Row gutter={[12, 12]} style={{ marginBottom: 12 }}>
                      <Col xs={12} sm={8}>
                        <Statistic
                          title="本周已服"
                          value={weekly.medication.taken}
                          prefix={<MedicineBoxOutlined style={{ color: '#52c41a' }} />}
                        />
                      </Col>
                      <Col xs={12} sm={8}>
                        <Statistic
                          title="本周漏服"
                          value={weekly.medication.missed}
                          prefix={<WarningOutlined style={{ color: '#ff4d4f' }} />}
                        />
                      </Col>
                      <Col xs={24} sm={8}>
                        <Statistic
                          title="依从率"
                          value={weekly.medication.adherence_rate}
                          suffix="%"
                          valueStyle={{ color: adherenceColor(weekly.medication.adherence_rate) }}
                        />
                      </Col>
                    </Row>

                    {weekly.new_symptoms_discussed.length > 0 && (
                      <div style={{ marginBottom: 12 }}>
                        <Text strong>
                          <MessageOutlined style={{ marginRight: 4 }} />
                          本周新讨论的症状
                        </Text>
                        <div style={{ marginTop: 6 }}>
                          {weekly.new_symptoms_discussed.slice(0, 5).map((s, idx) => (
                            <Tag key={idx} style={{ marginBottom: 4, whiteSpace: 'normal' }}>
                              {s.content}
                            </Tag>
                          ))}
                        </div>
                      </div>
                    )}

                    {weekly.upcoming_refills.length > 0 && (
                      <div>
                        <Text strong>
                          <MedicineBoxOutlined style={{ marginRight: 4, color: '#fa8c16' }} />
                          需要补货的药品
                        </Text>
                        <div style={{ marginTop: 6 }}>
                          {weekly.upcoming_refills.map((r, idx) => (
                            <Tag key={idx} color="orange" style={{ marginBottom: 4 }}>
                              {r.name}
                              {r.quantity !== undefined ? `（库存 ${r.quantity}）` : ''}
                              {r.expiry_date ? `（${r.expiry_date}）` : ''}
                              {' · '}
                              {r.reason}
                            </Tag>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                ) : (
                  <Empty description="暂无周报数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                )}
              </Card>
            </Space>
          )}
        </Col>
      </Row>

      {/* Section 3 — 提醒阈值 Modal */}
      <Modal
        title={
          <Space>
            <SettingOutlined />
            <span>设置提醒阈值 — {selectedUser?.sharer_name}</span>
          </Space>
        }
        open={alertModalOpen}
        onOk={handleSaveAlert}
        onCancel={() => setAlertModalOpen(false)}
        confirmLoading={savingAlert}
        okText="保存"
        cancelText="取消"
        destroyOnClose
      >
        <Form form={alertForm} layout="vertical">
          <Form.Item
            name="missed_reminder_threshold"
            label="漏服提醒阈值（次/日）"
            tooltip="当日漏服次数达到此值时触发提醒"
          >
            <InputNumber min={0} max={100} style={{ width: '100%' }} placeholder="如：2" />
          </Form.Item>
          <Form.Item
            name="expired_medicine_alert"
            label="过期药品预警"
            valuePropName="checked"
            tooltip="开启后将自动检测药箱中的过期药品"
          >
            <Switch checkedChildren="开" unCheckedChildren="关" />
          </Form.Item>
          <Form.Item
            name="low_stock_threshold"
            label="低库存阈值"
            tooltip="库存低于此值时触发提醒"
          >
            <InputNumber min={0} max={999} style={{ width: '100%' }} placeholder="如：7" />
          </Form.Item>
        </Form>
      </Modal>

      {/* Section 4 — 邀请家属 Modal */}
      <Modal
        title={
          <Space>
            <UserAddOutlined />
            <span>邀请家属</span>
          </Space>
        }
        open={inviteModalOpen}
        onOk={handleInvite}
        onCancel={() => {
          setInviteModalOpen(false);
          inviteForm.resetFields();
        }}
        confirmLoading={inviting}
        okText="发送邀请"
        cancelText="取消"
        destroyOnClose
      >
        <Alert
          type="info"
          showIcon
          message="邀请前请确保被邀请人已在本系统注册账户，并且您已同意数据共享。"
          style={{ marginBottom: 16 }}
        />
        <Form form={inviteForm} layout="vertical">
          <Form.Item
            name="username"
            label="被邀请人用户名"
            rules={[{ required: true, message: '请输入用户名' }, { min: 2, max: 50 }]}
          >
            <Input placeholder="请输入对方用户名" prefix={<UserOutlined />} />
          </Form.Item>
        </Form>
        <Divider style={{ margin: '12px 0' }} />
        <Paragraph type="secondary" style={{ fontSize: 14 }}>
          <SafetyOutlined /> 邀请后对方将以「家属查看」身份查看您的健康数据，您可随时撤销共享。
        </Paragraph>
      </Modal>
    </div>
  );
}

