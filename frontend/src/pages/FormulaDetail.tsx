import { useState, useEffect, useRef } from 'react';
import {
  Descriptions,
  Button,
  Skeleton,
  Typography,
  Tag,
  message,
  Divider,
  List,
  Modal,
  Input,
  DatePicker,
  Space,
  Alert,
  Card,
} from 'antd';
import {
  ArrowLeftOutlined,
  StarOutlined,
  StarFilled,
  ExperimentOutlined,
  PrinterOutlined,
  SafetyOutlined,
  PlusCircleOutlined,
  BranchesOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import { useParams, useNavigate } from 'react-router-dom';
import { getFormula, type Formula, type ModificationItem } from '../api/formulaApi';
import { createFavorite, deleteFavorite, checkFavorite } from '../api/favoriteApi';
import { request } from '../api/client';
import { useIsMobile } from '../hooks/useIsMobile';

const { Title, Text } = Typography;

interface HerbRole {
  name: string;
  role: string;
  dosage: string;
  rationale: string;
}

const ROLE_COLOR: Record<string, string> = {
  君药: 'red',
  臣药: 'orange',
  佐药: 'blue',
  使药: 'green',
};

const ROLE_PRINT_LABEL: Record<string, string> = {
  君药: '君',
  臣药: '臣',
  佐药: '佐',
  使药: '使',
};

/** Normalize modification data into a uniform list of items. */
function parseModifications(formula: Formula): ModificationItem[] {
  if (
    Array.isArray(formula.modifications_structured) &&
    formula.modifications_structured.length > 0
  ) {
    return formula.modifications_structured;
  }
  if (Array.isArray(formula.modifications) && formula.modifications.length > 0) {
    const objs = formula.modifications.filter(
      (m): m is ModificationItem => typeof m === 'object' && m !== null,
    );
    if (objs.length > 0) return objs;
    const strs = formula.modifications.filter(
      (m): m is string => typeof m === 'string',
    );
    if (strs.length > 0) return strs.map((m) => ({ note: m }));
  }
  if (
    typeof formula.modifications === 'string' &&
    formula.modifications.trim()
  ) {
    return [{ note: formula.modifications }];
  }
  return [];
}

export default function FormulaDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const [formula, setFormula] = useState<Formula | null>(null);
  const [loading, setLoading] = useState(true);
  const [isFavorite, setIsFavorite] = useState(false);
  const [favoriteId, setFavoriteId] = useState<string | null>(null);
  const [herbRoles, setHerbRoles] = useState<HerbRole[]>([]);
  const [printOpen, setPrintOpen] = useState(false);
  const [patientName, setPatientName] = useState('');
  const [prescriber, setPrescriber] = useState('');
  const [prescribeDate, setPrescribeDate] = useState<dayjs.Dayjs>(dayjs());
  const [notes, setNotes] = useState('');
  const [parentFormulaName, setParentFormulaName] = useState<string | null>(null);
  const printRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!id) return;
    const load = async () => {
      setLoading(true);
      try {
        const data = await getFormula(id);
        setFormula(data);
        const check = await checkFavorite('formula', id);
        setIsFavorite(check.exists);
        setFavoriteId(check.favorite_id ?? null);
        const rolesData = await request<{ herb_roles: HerbRole[] }>(
          `/api/formulas/${id}/roles`,
        );
        setHerbRoles(rolesData.herb_roles ?? []);
      } catch {
        // handled
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [id]);

  useEffect(() => {
    if (!formula?.derived_from_id) {
      setParentFormulaName(null);
      return;
    }
    let cancelled = false;
    getFormula(formula.derived_from_id)
      .then((parent) => {
        if (!cancelled) setParentFormulaName(parent.name);
      })
      .catch(() => {
        if (!cancelled) setParentFormulaName(null);
      });
    return () => {
      cancelled = true;
    };
  }, [formula?.derived_from_id]);

  const handleToggleFavorite = async () => {
    if (!formula || !id) return;
    try {
      if (isFavorite && favoriteId) {
        await deleteFavorite(favoriteId);
        setIsFavorite(false);
        setFavoriteId(null);
        message.success('已取消收藏');
      } else {
        const fav = await createFavorite({
          entry_type: 'formula',
          title: formula.name,
          content: `组成：${formula.composition}。功效：${formula.efficacy}`,
          summary: formula.efficacy,
          source_type: 'formula',
          source_url: id,
        });
        setIsFavorite(true);
        setFavoriteId(fav.id);
        message.success('已收藏');
      }
    } catch {
      message.error('操作失败');
    }
  };

  const handlePrint = () => {
    setPrintOpen(false);
    setTimeout(() => window.print(), 100);
  };

  if (loading) return <Skeleton active />;
  if (!formula) return <div>方剂未找到</div>;

  return (
    <div className="formula-detail-page">
      <Button
        icon={<ArrowLeftOutlined />}
        onClick={() => navigate('/formulas')}
        style={{ marginBottom: 16 }}
        className="no-print"
      >
        返回列表
      </Button>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }} className="no-print">
        <Title level={3} style={{ margin: 0 }}>{formula.name}</Title>
        <Space>
          <Button
            type="text"
            icon={isFavorite ? <StarFilled style={{ color: '#faad14', fontSize: 20 }} /> : <StarOutlined style={{ fontSize: 20 }} />}
            onClick={handleToggleFavorite}
          >
            {isFavorite ? '已收藏' : '收藏'}
          </Button>
          <Button
            icon={<SafetyOutlined />}
            onClick={() => navigate(`/safety?herbs=${encodeURIComponent(formula.composition)}`)}
          >
            安全检查
          </Button>
          <Button
            type="primary"
            icon={<PrinterOutlined />}
            onClick={() => setPrintOpen(true)}
          >
            导出处方单
          </Button>
        </Space>
      </div>
      {formula.derived_from_id && (
        <Alert
          className="no-print"
          type="info"
          showIcon
          icon={<BranchesOutlined />}
          style={{ marginBottom: 16 }}
          message={
            <Space>
              <Text>本方源于：</Text>
              <Text strong>{parentFormulaName ?? '源方剂'}</Text>
            </Space>
          }
          action={
            <Button
              onClick={() => navigate(`/formulas/${formula.derived_from_id}`)}
            >
              查看源方
            </Button>
          }
        />
      )}
      <Descriptions column={1} bordered className="no-print">
        <Descriptions.Item label="分类">{formula.category}</Descriptions.Item>
        <Descriptions.Item label="组成">
          {formula.composition}
        </Descriptions.Item>
        <Descriptions.Item label="功效">{formula.efficacy}</Descriptions.Item>
        <Descriptions.Item label="主治">
          {formula.indication}
        </Descriptions.Item>
        <Descriptions.Item label="用法">{formula.usage}</Descriptions.Item>
        <Descriptions.Item label="描述">
          {formula.description}
        </Descriptions.Item>
      </Descriptions>

      {herbRoles.length > 0 && (
        <>
          <Divider className="no-print" />
          <Title level={4} className="no-print">
            <ExperimentOutlined style={{ marginRight: 8 }} />
            君臣佐使拆解
          </Title>
          <List
            className="no-print"
            dataSource={herbRoles}
            renderItem={(item) => (
              <List.Item>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, width: '100%' }}>
                  <Tag color={ROLE_COLOR[item.role] ?? 'default'} style={{ minWidth: 50, textAlign: 'center' }}>
                    {item.role}
                  </Tag>
                  <Text strong style={{ fontSize: 16 }}>{item.name}</Text>
                  <Text type="secondary">{item.dosage}</Text>
                  <Text style={{ color: '#666', marginLeft: 'auto' }}>{item.rationale}</Text>
                </div>
              </List.Item>
            )}
          />
        </>
      )}

      {(() => {
        const mods = parseModifications(formula);
        if (mods.length === 0) return null;
        return (
          <>
            <Divider className="no-print" />
            <Title level={4} className="no-print">
              <PlusCircleOutlined style={{ marginRight: 8 }} />
              加减变化
            </Title>
            <List
              className="no-print"
              dataSource={mods}
              renderItem={(mod) => (
                <List.Item>
                  <Card size="small" style={{ width: '100%' }} bordered>
                    <Space direction="vertical" style={{ width: '100%' }} size="small">
                      {mod.symptom && (
                        <Text strong style={{ fontSize: 15 }}>{mod.symptom}</Text>
                      )}
                      {mod.action && (
                        <Text>{mod.action}</Text>
                      )}
                      {(mod.add?.length || mod.remove?.length) ? (
                        <Space wrap>
                          {mod.add && mod.add.length > 0 && (
                            <>
                              <Text type="secondary">加：</Text>
                              {mod.add.map((h) => (
                                <Tag color="green" key={h}>{h}</Tag>
                              ))}
                            </>
                          )}
                          {mod.remove && mod.remove.length > 0 && (
                            <>
                              <Text type="secondary">减：</Text>
                              {mod.remove.map((h) => (
                                <Tag color="red" key={h}>{h}</Tag>
                              ))}
                            </>
                          )}
                        </Space>
                      ) : null}
                      {mod.note && (
                        <Text type="secondary">{mod.note}</Text>
                      )}
                    </Space>
                  </Card>
                </List.Item>
              )}
            />
          </>
        );
      })()}

      <Modal
        title="处方单预览"
        open={printOpen}
        onCancel={() => setPrintOpen(false)}
        width={isMobile ? '100%' : 600}
        className="no-print"
        footer={
          <Space>
            <Button onClick={() => setPrintOpen(false)}>取消</Button>
            <Button type="primary" icon={<PrinterOutlined />} onClick={handlePrint}>
              打印 / 保存PDF
            </Button>
          </Space>
        }
      >
        <div style={{ marginBottom: 16 }}>
          <Space wrap>
            <Input
              placeholder="患者姓名"
              value={patientName}
              onChange={(e) => setPatientName(e.target.value)}
              style={{ width: 150 }}
              addonBefore="姓名"
            />
            <Input
              placeholder="医者签名"
              value={prescriber}
              onChange={(e) => setPrescriber(e.target.value)}
              style={{ width: 150 }}
              addonBefore="医者"
            />
            <span>日期：</span>
            <DatePicker
              value={prescribeDate}
              onChange={(d) => d && setPrescribeDate(d)}
            />
          </Space>
          <Input.TextArea
            placeholder="医嘱备注（可选）"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            style={{ marginTop: 8 }}
          />
        </div>
      </Modal>

      {/* Print-only prescription sheet */}
      <div ref={printRef} className="print-only">
        <div className="rx-sheet">
          <div className="rx-header">
            <h1>处 方 单</h1>
            <div className="rx-clinic-name">家庭医生 · 养生助手</div>
          </div>
          <div className="rx-info">
            <span>患者：{patientName || '____'}</span>
            <span>日期：{prescribeDate.format('YYYY年MM月DD日')}</span>
            <span>医者：{prescriber || '____'}</span>
          </div>
          <div className="rx-formula-name">{formula.name}</div>
          <div className="rx-efficacy">功效：{formula.efficacy}</div>
          <div className="rx-indication">主治：{formula.indication}</div>
          {herbRoles.length > 0 && (
            <table className="rx-herbs-table">
              <thead>
                <tr>
                  <th style={{ width: 50 }}>角色</th>
                  <th>药材</th>
                  <th style={{ width: 80 }}>用量</th>
                </tr>
              </thead>
              <tbody>
                {herbRoles.map((h, i) => (
                  <tr key={i}>
                    <td className="rx-role-cell">{ROLE_PRINT_LABEL[h.role] ?? h.role}</td>
                    <td className="rx-herb-name">{h.name}</td>
                    <td>{h.dosage}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div className="rx-composition">
            <strong>组成：</strong>{formula.composition}
          </div>
          <div className="rx-usage">
            <strong>用法：</strong>{formula.usage}
          </div>
          {notes && (
            <div className="rx-notes">
              <strong>医嘱：</strong>{notes}
            </div>
          )}
          <div className="rx-footer">
            <p className="rx-disclaimer">
              ⚠ 本处方仅供参考，实际用药请遵医嘱。药物配伍、剂量、禁忌请咨询专业中医师。
            </p>
            <div className="rx-signature">签名：_____________</div>
          </div>
        </div>
      </div>

      <style>{`
        .print-only { display: none; }

        @media print {
          body * { visibility: hidden; }
          .print-only, .print-only * { visibility: visible; }
          .print-only {
            display: block !important;
            position: absolute;
            left: 0;
            top: 0;
            width: 100%;
          }
          .no-print { display: none !important; }

          .rx-sheet {
            max-width: 210mm;
            margin: 0 auto;
            padding: 20mm 15mm;
            font-family: "Songti SC", "SimSun", "Noto Serif SC", serif;
            color: #1a1a1a;
          }
          .rx-header {
            text-align: center;
            border-bottom: 2px solid #333;
            padding-bottom: 12px;
            margin-bottom: 16px;
          }
          .rx-header h1 {
            font-size: 28px;
            letter-spacing: 12px;
            margin: 0 0 4px 0;
          }
          .rx-clinic-name {
            font-size: 14px;
            color: #666;
          }
          .rx-info {
            display: flex;
            justify-content: space-between;
            font-size: 14px;
            margin-bottom: 16px;
            padding: 8px 0;
            border-bottom: 1px dashed #ccc;
          }
          .rx-formula-name {
            font-size: 24px;
            font-weight: bold;
            text-align: center;
            margin: 16px 0 8px;
          }
          .rx-efficacy, .rx-indication {
            font-size: 14px;
            margin: 4px 0;
            color: #444;
          }
          .rx-herbs-table {
            width: 100%;
            border-collapse: collapse;
            margin: 12px 0;
            font-size: 16px;
          }
          .rx-herbs-table th {
            background: #f5f5f5;
            border: 1px solid #ddd;
            padding: 8px 12px;
            text-align: center;
            font-weight: 600;
          }
          .rx-herbs-table td {
            border: 1px solid #ddd;
            padding: 8px 12px;
          }
          .rx-role-cell {
            text-align: center;
            font-weight: bold;
            color: #c41e3a;
          }
          .rx-herb-name {
            font-size: 18px;
            font-weight: 500;
          }
          .rx-composition, .rx-usage, .rx-notes {
            font-size: 14px;
            margin: 6px 0;
            line-height: 1.8;
          }
          .rx-footer {
            margin-top: 24px;
            padding-top: 12px;
            border-top: 1px solid #ccc;
          }
          .rx-disclaimer {
            font-size: 14px;
            color: #666;
            line-height: 1.6;
          }
          .rx-signature {
            margin-top: 16px;
            text-align: right;
            font-size: 14px;
          }
          @page {
            size: A4;
            margin: 0;
          }
        }
      `}</style>
    </div>
  );
}
