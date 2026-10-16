import { useEffect, useRef, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Typography,
  Select,
  Input,
  Button,
  Space,
  message,
  Spin,
  Empty,
  Tag,
  Drawer,
  Descriptions,
  Tooltip,
  Popconfirm,
} from 'antd';
import type { Graph, NodeData, EdgeData, IElementEvent } from '@antv/g6';
import {
  ReloadOutlined,
  SearchOutlined,
  AimOutlined,
  FullscreenOutlined,
  ApartmentOutlined,
  FilterOutlined,
  RetweetOutlined,
} from '@ant-design/icons';
import { getGraph, getSnapshot, rebuildGraph, getNode } from '../api/graphApi';
import type {
  GraphData,
  GraphNodeDetail,
  NodeType,
} from '../api/graphApi';
import { ApiError } from '../api/client';
import { useIsMobile } from '../hooks/useIsMobile';

const { Title, Text } = Typography;

const NODE_TYPES: { value: NodeType; label: string }[] = [
  { value: 'herb', label: '中药' },
  { value: 'formula', label: '方剂' },
  { value: 'symptom', label: '症状' },
  { value: 'therapy', label: '疗法' },
  { value: 'medicine', label: '西药' },
];

const NODE_TYPE_LABEL: Record<string, string> = {
  herb: '中药',
  formula: '方剂',
  symptom: '症状',
  therapy: '疗法',
  medicine: '西药',
};

const TYPE_COLORS: Record<string, string> = {
  herb: '#52c41a',
  formula: '#1890ff',
  symptom: '#faad14',
  therapy: '#722ed1',
  medicine: '#eb2f96',
};

const EDGE_COLORS: Record<string, string> = {
  组成: '#1890ff',
  主治: '#52c41a',
  配伍禁忌: '#ff4d4f',
  中西药交互: '#faad14',
};

type LayoutKind = 'd3-force' | 'dagre' | 'radial';

function strField(datum: NodeData | EdgeData, key: string): string {
  const d = datum.data;
  const v = d === undefined ? undefined : d[key];
  return typeof v === 'string' ? v : '';
}

function nodeFill(datum: NodeData): string {
  return TYPE_COLORS[strField(datum, 'nodeType')] ?? '#666';
}

function nodeLabelText(datum: NodeData): string {
  const label = strField(datum, 'label');
  return label || String(datum.id ?? '');
}

function edgeStroke(datum: EdgeData): string {
  return EDGE_COLORS[strField(datum, 'edgeType')] ?? '#666';
}

function toG6(snapshot: GraphData) {
  const nodes: NodeData[] = snapshot.nodes.map((n) => ({
    id: n.id,
    data: { label: n.label, nodeType: n.node_type },
  }));
  const edges: EdgeData[] = snapshot.edges.map((e, i) => ({
    id: `${e.source}->${e.target}:${e.edge_type}`,
    source: e.source,
    target: e.target,
    data: { edgeType: e.edge_type, _idx: i },
  }));
  return { nodes, edges };
}

export default function KnowledgeGraphPage() {
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const containerRef = useRef<HTMLDivElement>(null);
  const graphRef = useRef<Graph | null>(null);
  const idsRef = useRef<Set<string>>(new Set());
  const baseIdsRef = useRef<Set<string>>(new Set());
  const addedByRef = useRef<Map<string, Set<string>>>(new Map());
  const expandedRef = useRef<Set<string>>(new Set());
  const clickTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const navRef = useRef(navigate);
  navRef.current = navigate;

  const [types, setTypes] = useState<string[]>([]);
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const [count, setCount] = useState<{ nodes: number; edges: number }>({
    nodes: 0,
    edges: 0,
  });
  const [presentTypes, setPresentTypes] = useState<string[]>([]);
  const [presentEdgeTypes, setPresentEdgeTypes] = useState<string[]>([]);
  const [hiddenNodeTypes, setHiddenNodeTypes] = useState<string[]>([]);
  const [hiddenEdgeTypes, setHiddenEdgeTypes] = useState<string[]>([]);
  const [layoutType, setLayoutType] = useState<LayoutKind>('d3-force');
  const [detailNode, setDetailNode] = useState<GraphNodeDetail | null>(null);
  const [detailType, setDetailType] = useState<string>('');
  const [detailLoading, setDetailLoading] = useState(false);

  const refreshStats = useCallback((graph: Graph) => {
    const nodes = graph.getNodeData();
    const edges = graph.getEdgeData();
    setCount({ nodes: nodes.length, edges: edges.length });
    setPresentTypes(
      Array.from(
        new Set(nodes.map((n) => strField(n, 'nodeType')).filter(Boolean)),
      ),
    );
    setPresentEdgeTypes(
      Array.from(
        new Set(edges.map((e) => strField(e, 'edgeType')).filter(Boolean)),
      ),
    );
  }, []);

  const handleApiError = useCallback((e: unknown) => {
    if (e instanceof ApiError) {
      void message.error(e.message);
    } else {
      void message.error('网络错误，请稍后重试');
    }
  }, []);

  const fetchAndSet = useCallback(
    async (graph: Graph) => {
      setLoading(true);
      try {
        const snap = await getGraph({
          types: types.length ? types.join(',') : undefined,
          q: q.trim() || undefined,
          limit: 500,
        });
        if (graph.destroyed) return;
        const data = toG6(snap);
        idsRef.current = new Set(data.nodes.map((n) => n.id));
        baseIdsRef.current = new Set(idsRef.current);
        addedByRef.current = new Map();
        expandedRef.current = new Set();
        graph.setData(data);
        await graph.render();
        refreshStats(graph);
      } catch (e) {
        handleApiError(e);
      } finally {
        setLoading(false);
      }
    },
    [types, q, refreshStats, handleApiError],
  );

  const expandNode = useCallback(
    async (graph: Graph, nodeId: string, nodeType: string) => {
      try {
        const snap = await getSnapshot(nodeType, nodeId, 1);
        if (graph.destroyed) return;
        const data = toG6(snap);
        const newNodes = data.nodes.filter((n) => !idsRef.current.has(n.id));
        for (const n of newNodes) {
          if (!addedByRef.current.has(n.id)) {
            addedByRef.current.set(n.id, new Set());
          }
          addedByRef.current.get(n.id)!.add(nodeId);
          idsRef.current.add(n.id);
        }
        if (newNodes.length) graph.addNodeData(newNodes);
        const existingEdgeIds = new Set(graph.getEdgeData().map((e) => e.id));
        const newEdges = data.edges.filter(
          (e) =>
            !existingEdgeIds.has(e.id) &&
            idsRef.current.has(e.source) &&
            idsRef.current.has(e.target),
        );
        if (newEdges.length) graph.addEdgeData(newEdges);
        expandedRef.current.add(nodeId);
        await graph.render();
        refreshStats(graph);
        if (newNodes.length === 0) {
          void message.info('该节点没有更多可展开的关联(再次双击可折叠)');
        }
      } catch (e) {
        handleApiError(e);
      }
    },
    [refreshStats, handleApiError],
  );

  const collapseNode = useCallback(
    async (graph: Graph, nodeId: string) => {
      const toRemove: string[] = [];
      for (const [neighbor, holders] of addedByRef.current) {
        if (!holders.has(nodeId)) continue;
        holders.delete(nodeId);
        if (holders.size === 0 && !baseIdsRef.current.has(neighbor)) {
          toRemove.push(neighbor);
        }
      }
      expandedRef.current.delete(nodeId);
      if (toRemove.length === 0) {
        void message.info('该节点的关联已被其它节点共享，无可折叠项');
        return;
      }
      for (const id of toRemove) {
        idsRef.current.delete(id);
        addedByRef.current.delete(id);
        expandedRef.current.delete(id);
      }
      if (graph.destroyed) return;
      try {
        graph.removeNodeData(toRemove);
        await graph.render();
        refreshStats(graph);
      } catch (e) {
        handleApiError(e);
      }
    },
    [refreshStats, handleApiError],
  );

  const openDetail = useCallback(async (nodeId: string, nodeType: string) => {
    setDetailType(nodeType);
    setDetailLoading(true);
    setDetailNode(null);
    try {
      setDetailNode(await getNode(nodeId));
    } catch {
      setDetailNode(null);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const applyNodeFilter = useCallback(
    (graph: Graph, hidden: string[]) => {
      if (graph.destroyed) return;
      const hideSet = new Set(hidden);
      const nodes = graph.getNodeData();
      void Promise.all(
        nodes.map((n) =>
          graph.setElementVisibility(
            n.id,
            hideSet.has(strField(n, 'nodeType')) ? 'hidden' : 'visible',
          ),
        ),
      );
    },
    [],
  );

  const applyEdgeFilter = useCallback((graph: Graph, hidden: string[]) => {
    if (graph.destroyed) return;
    const hideSet = new Set(hidden);
    const edges = graph.getEdgeData();
    void Promise.all(
      edges.map((e) =>
        e.id === undefined
          ? Promise.resolve()
          : graph.setElementVisibility(
              e.id,
              hideSet.has(strField(e, 'edgeType')) ? 'hidden' : 'visible',
            ),
      ),
    );
  }, []);

  const switchLayout = useCallback(
    async (graph: Graph, kind: LayoutKind) => {
      if (graph.destroyed) return;
      const config: Record<string, unknown> =
        kind === 'dagre'
          ? { type: 'dagre', rankdir: 'TB', nodesep: 30, ranksep: 60 }
          : kind === 'radial'
            ? { type: 'radial', unitRadius: 80, linkDistance: 100 }
            : { type: 'd3-force', collide: { radius: 40 }, link: { distance: 120 } };
      try {
        graph.setLayout(config as Parameters<typeof graph.setLayout>[0]);
        await graph.render();
        await graph.fitView();
      } catch (e) {
        handleApiError(e);
      }
    },
    [handleApiError],
  );

  const locateInGraph = useCallback(
    async (graph: Graph) => {
      if (graph.destroyed) return;
      const kw = q.trim().toLowerCase();
      if (!kw) {
        await fetchAndSet(graph);
        return;
      }
      const nodes = graph.getNodeData();
      const hit = nodes.find((n) =>
        nodeLabelText(n).toLowerCase().includes(kw),
      );
      if (hit) {
        try {
          await graph.focusElement(hit.id);
          void message.success(`定位到「${nodeLabelText(hit)}」`);
        } catch {
          await fetchAndSet(graph);
        }
      } else {
        await fetchAndSet(graph);
      }
    },
    [q, fetchAndSet],
  );

  const doRebuild = useCallback(async () => {
    setRebuilding(true);
    try {
      const result = await rebuildGraph();
      void message.success(
        `重建完成：组成 ${result.组成} · 主治 ${result.主治} · 配伍禁忌 ${result.配伍禁忌} · 中西药交互 ${result.中西药交互}`,
      );
      if (graphRef.current && !graphRef.current.destroyed) {
        await fetchAndSet(graphRef.current);
      }
    } catch (e) {
      handleApiError(e);
    } finally {
      setRebuilding(false);
    }
  }, [fetchAndSet, handleApiError]);

  useEffect(() => {
    if (!containerRef.current || graphRef.current) return;
    let graph: Graph;
    import('@antv/g6').then(({ Graph: G6Graph }) => {
      if (!containerRef.current || graphRef.current) return;
      graph = new G6Graph({
        container: containerRef.current,
        autoResize: true,
        animation: false,
        layout: {
          type: 'd3-force',
          collide: { radius: 40 },
          link: { distance: 120 },
        },
        node: {
          style: {
            size: 30,
            fill: nodeFill,
            stroke: '#fff',
            lineWidth: 1.5,
            labelText: nodeLabelText,
            labelfontSize: 14,
            labelFill: '#333',
            labelPlacement: 'bottom',
            labelBackground: true,
            labelBackgroundFill: 'rgba(255,255,255,0.75)',
          },
        },
        edge: {
          style: {
            stroke: edgeStroke,
            endArrow: true,
            lineWidth: 1.5,
          },
        },
        behaviors: ['zoom-canvas', 'drag-canvas', 'drag-element', 'hover-activate'],
        plugins: [{ type: 'minimap', size: [140, 90], key: 'kg-minimap' }],
      });
      graphRef.current = graph;

      graph.on('node:click', (e: IElementEvent) => {
        const id = e.target.id;
        if (!id) return;
        if (clickTimerRef.current) clearTimeout(clickTimerRef.current);
        clickTimerRef.current = setTimeout(() => {
          clickTimerRef.current = null;
          if (graph.destroyed) return;
          try {
            const nd = graph.getNodeData(id);
            const nodeType = strField(nd, 'nodeType');
            if (nodeType) void openDetail(id, nodeType);
          } catch {
            /* node may have been removed */
          }
        }, 260);
      });

      graph.on('node:dblclick', (e: IElementEvent) => {
        const id = e.target.id;
        if (!id) return;
        if (clickTimerRef.current) {
          clearTimeout(clickTimerRef.current);
          clickTimerRef.current = null;
        }
        try {
          const nd = graph.getNodeData(id);
          const nodeType = strField(nd, 'nodeType');
          if (!nodeType) return;
          if (expandedRef.current.has(id)) {
            void collapseNode(graph, id);
          } else {
            void expandNode(graph, id, nodeType);
          }
        } catch {
          /* ignore */
        }
      });

      void fetchAndSet(graph);
    });

    return () => {
      if (clickTimerRef.current) clearTimeout(clickTimerRef.current);
      if (graphRef.current) {
        try {
          graphRef.current.destroy();
        } catch {
          /* ignore double-destroy */
        }
        graphRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const reload = () => {
    if (graphRef.current) void fetchAndSet(graphRef.current);
  };

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 16,
          flexWrap: 'wrap',
          gap: 8,
        }}
      >
        <Space>
          <Title level={4} style={{ margin: 0 }}>
            知识图谱
          </Title>
          <Text type="secondary" style={{ fontSize: 14 }}>
            中药·方剂·症状·疗法关系网络
          </Text>
        </Space>
        <Space wrap>
          <Select
            mode="multiple"
            allowClear
            style={{ minWidth: 220 }}
            placeholder="按类型筛选(默认全部)"
            value={types}
            onChange={setTypes}
            options={NODE_TYPES}
            maxTagCount="responsive"
          />
          <Input
            style={{ width: 200 }}
            placeholder="搜索关键词"
            prefix={<SearchOutlined />}
            allowClear
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onPressEnter={() => graphRef.current && locateInGraph(graphRef.current)}
          />
          <Tooltip title="在当前图中定位关键词命中的节点">
            <Button
              icon={<AimOutlined />}
              onClick={() => graphRef.current && locateInGraph(graphRef.current)}
            >
              定位
            </Button>
          </Tooltip>
          <Button
            type="primary"
            icon={<ReloadOutlined />}
            onClick={reload}
            loading={loading}
          >
            刷新
          </Button>
          <Popconfirm
            title="重建图谱"
            description="将清除所有派生边并从结构化数据重新生成，确认继续？"
            onConfirm={doRebuild}
            okText="确认重建"
            cancelText="取消"
          >
            <Button icon={<RetweetOutlined />} loading={rebuilding}>
              重建图谱
            </Button>
          </Popconfirm>
        </Space>
      </div>

      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 8,
          flexWrap: 'wrap',
          gap: 8,
        }}
      >
        <Text type="secondary" style={{ fontSize: 14 }}>
          单击查看详情 · 双击展开/折叠关联 · 当前 {count.nodes} 节点 / {count.edges}{' '}
          关系
        </Text>
        <Space size={12} wrap>
          {presentEdgeTypes.map((t) => (
            <span
              key={t}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}
            >
              <span
                style={{
                  display: 'inline-block',
                  width: 16,
                  height: 3,
                  borderRadius: 2,
                  background: EDGE_COLORS[t] ?? '#666',
                }}
              />
              <Text style={{ fontSize: 14 }}>{t}</Text>
            </span>
          ))}
        </Space>
        <Space size={4} wrap>
          {presentTypes.length > 0 && (
            <Select
              mode="multiple"
              allowClear
              suffixIcon={<FilterOutlined />}
              style={{ minWidth: 160 }}
              placeholder="隐藏节点类型"
              value={hiddenNodeTypes}
              onChange={(v) => {
                setHiddenNodeTypes(v);
                if (graphRef.current) applyNodeFilter(graphRef.current, v);
              }}
              options={presentTypes.map((t) => ({
                value: t,
                label: NODE_TYPE_LABEL[t] ?? t,
              }))}
              maxTagCount="responsive"
            />
          )}
          {presentEdgeTypes.length > 0 && (
            <Select
              mode="multiple"
              allowClear
              suffixIcon={<FilterOutlined />}
              style={{ minWidth: 160 }}
              placeholder="隐藏边类型"
              value={hiddenEdgeTypes}
              onChange={(v) => {
                setHiddenEdgeTypes(v);
                if (graphRef.current) applyEdgeFilter(graphRef.current, v);
              }}
              options={presentEdgeTypes.map((t) => ({ value: t, label: t }))}
              maxTagCount="responsive"
            />
          )}
          <Select
            value={layoutType}
            onChange={(v) => {
              setLayoutType(v);
              if (graphRef.current) void switchLayout(graphRef.current, v);
            }}
            style={{ width: 110 }}
            suffixIcon={<ApartmentOutlined />}
            options={[
              { value: 'd3-force', label: '力导向' },
              { value: 'dagre', label: '层次' },
              { value: 'radial', label: '辐射' },
            ]}
          />
          <Tooltip title="适应画布">
            <Button
              icon={<FullscreenOutlined />}
              onClick={() => {
                try {
                  void graphRef.current?.fitView();
                } catch {
                  /* ignore */
                }
              }}
            />
          </Tooltip>
        </Space>
      </div>

      <Spin spinning={loading}>
        <div
          style={{
            position: 'relative',
            border: '1px solid #f0f0f0',
            borderRadius: 8,
            background: '#fafafa',
          }}
        >
          <div
            ref={containerRef}
            style={{
              width: '100%',
              height: 'calc(100vh - 200px)',
              minHeight: 420,
            }}
          />
          {!loading && count.nodes === 0 && (
            <div
              style={{
                position: 'absolute',
                inset: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Empty description="暂无图谱数据，点击「重建图谱」从已有数据生成" />
            </div>
          )}
        </div>
      </Spin>

      <Drawer
        title={
          detailNode ? (
            <Space>
              <Text strong>{detailNode.label}</Text>
              <Tag color={TYPE_COLORS[detailType] ?? 'default'}>
                {NODE_TYPE_LABEL[detailType] ?? detailType}
              </Tag>
            </Space>
          ) : (
            '节点详情'
          )
        }
        open={!!detailNode || detailLoading}
        onClose={() => {
          setDetailNode(null);
          setDetailType('');
        }}
        width={isMobile ? '100%' : 480}
        destroyOnClose
        maskClosable={false}
        extra={
          detailNode &&
          graphRef.current && (
            <Space>
              {expandedRef.current.has(detailNode.id) ? (
                <Button
                  onClick={() => {
                    if (graphRef.current && detailNode) {
                      void collapseNode(graphRef.current, detailNode.id);
                    }
                    setDetailNode(null);
                  }}
                >
                  折叠关联
                </Button>
              ) : (
                <Button
                  type="primary"
                  onClick={() => {
                    if (graphRef.current && detailNode) {
                      void expandNode(
                        graphRef.current,
                        detailNode.id,
                        detailType,
                      );
                    }
                    setDetailNode(null);
                  }}
                >
                  展开 1 跳
                </Button>
              )}
            </Space>
          )
        }
      >
        {detailLoading && <Spin />}
        {detailNode && (
          <Descriptions bordered size="small" column={1}>
            <Descriptions.Item label="ID">{detailNode.id}</Descriptions.Item>
            {Object.entries(detailNode.properties)
              .filter(([, v]) => v != null && v !== '')
              .map(([k, v]) => (
                <Descriptions.Item key={k} label={k}>
                  {String(v)}
                </Descriptions.Item>
              ))}
            {detailNode.search_text && (
              <Descriptions.Item label="检索文本">
                {detailNode.search_text}
              </Descriptions.Item>
            )}
          </Descriptions>
        )}
      </Drawer>
    </div>
  );
}
