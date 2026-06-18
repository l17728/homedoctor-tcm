import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  Button,
  Skeleton,
  Empty,
  Typography,
  Tabs,
  Input,
  Tooltip,
  Badge,
  Tag,
  Spin,
  Drawer,
  message,
  theme,
} from 'antd';
import {
  ArrowLeftOutlined,
  RobotOutlined,
  EditOutlined,
  DeleteOutlined,
  SaveOutlined,
  TranslationOutlined,
  ThunderboltOutlined,
  CloseOutlined,
  FileTextOutlined,
  ReadOutlined,
  BulbOutlined,
} from '@ant-design/icons';
import { useParams, useNavigate } from 'react-router-dom';
import {
  getClassic,
  getChapter,
  createAnnotation,
  updateAnnotation,
  deleteAnnotation,
  askAI,
  translateChapter,
  saveTranslation,
  getStudyNotes,
  saveStudyNotes,
  summarize,
  type ClassicWithChapters,
  type ChapterDetail,
  type ClassicAnnotation,
  type AnnotationNoteType,
} from '../api/classicApi';
import { useIsMobile } from '../hooks/useIsMobile';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

type CenterTab = 'original' | 'translation' | 'notes';

interface SelectionInfo {
  start: number;
  end: number;
  text: string;
}

interface QAItem {
  question: string;
  answer: string;
}

// ─────────────────────────── 文本段切分（支持批注重叠） ───────────────────────────

interface TextSegment {
  text: string;
  start: number;
  end: number;
  annotations: ClassicAnnotation[];
}

function buildSegments(
  originalText: string,
  annotations: ClassicAnnotation[],
): TextSegment[] {
  if (!originalText) return [];
  const valid = annotations.filter(
    (a) =>
      a.start_offset >= 0 &&
      a.end_offset <= originalText.length &&
      a.start_offset < a.end_offset,
  );
  if (valid.length === 0) {
    return [{ text: originalText, start: 0, end: originalText.length, annotations: [] }];
  }
  const points = new Set<number>([0, originalText.length]);
  for (const a of valid) {
    points.add(a.start_offset);
    points.add(a.end_offset);
  }
  const sorted = Array.from(points).sort((x, y) => x - y);
  const segments: TextSegment[] = [];
  for (let i = 0; i < sorted.length - 1; i++) {
    const s = sorted[i]!;
    const e = sorted[i + 1]!;
    if (s >= e) continue;
    const text = originalText.slice(s, e);
    if (!text) continue;
    const covering = valid.filter((a) => a.start_offset <= s && a.end_offset >= e);
    segments.push({ text, start: s, end: e, annotations: covering });
  }
  return segments;
}

const NOTE_TYPE_COLOR: Record<AnnotationNoteType, string> = {
  annotation: 'rgba(255, 213, 79, 0.55)',
  qa_card: 'rgba(105, 160, 255, 0.42)',
  translation_note: 'rgba(126, 207, 138, 0.45)',
};

const NOTE_TYPE_LABEL: Record<AnnotationNoteType, string> = {
  annotation: '批注',
  qa_card: '问答卡',
  translation_note: '译注',
};

function highlightColor(annotations: ClassicAnnotation[]): string {
  if (annotations.some((a) => a.note_type === 'qa_card')) return NOTE_TYPE_COLOR.qa_card;
  if (annotations.some((a) => a.note_type === 'translation_note'))
    return NOTE_TYPE_COLOR.translation_note;
  return NOTE_TYPE_COLOR.annotation;
}

// ─────────────────────────── 选区偏移计算 ───────────────────────────

function getSelectionOffsets(
  container: HTMLElement,
): SelectionInfo | null {
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed || sel.rangeCount === 0) return null;
  const range = sel.getRangeAt(0);
  if (!container.contains(range.startContainer) || !container.contains(range.endContainer))
    return null;
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  let offset = 0;
  let start = -1;
  let end = -1;
  let node = walker.nextNode() as Text | null;
  while (node) {
    const len = node.nodeValue?.length ?? 0;
    if (node === range.startContainer) start = offset + range.startOffset;
    if (node === range.endContainer) end = offset + range.endOffset;
    offset += len;
    node = walker.nextNode() as Text | null;
  }
  if (start < 0 || end < 0 || start >= end) return null;
  const text = sel.toString();
  if (!text.trim()) return null;
  return { start, end, text };
}

function clearSelection() {
  const sel = window.getSelection();
  sel?.removeAllRanges();
}

// ─────────────────────────── 极简 Markdown 渲染 ───────────────────────────

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function inlineMd(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    .replace(/`([^`]+)`/g, '<code>$1</code>');
}

function renderMarkdown(md: string): string {
  if (!md) return '';
  const lines = md.split('\n');
  const out: string[] = [];
  let inUl = false;
  let inOl = false;
  let inCode = false;

  const closeLists = () => {
    if (inUl) {
      out.push('</ul>');
      inUl = false;
    }
    if (inOl) {
      out.push('</ol>');
      inOl = false;
    }
  };

  for (let i = 0; i < lines.length; i++) {
    let line = lines[i] ?? '';

    if (line.trim().startsWith('```')) {
      if (inCode) {
        out.push('</code></pre>');
        inCode = false;
      } else {
        closeLists();
        out.push('<pre><code>');
        inCode = true;
      }
      continue;
    }
    if (inCode) {
      out.push(escapeHtml(line));
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      closeLists();
      const level = (heading[1] ?? '#').length;
      out.push(`<h${level}>${inlineMd(heading[2] ?? '')}</h${level}>`);
      continue;
    }

    const ulItem = line.match(/^[-*+]\s+(.*)$/);
    if (ulItem) {
      if (!inUl) {
        closeLists();
        out.push('<ul>');
        inUl = true;
      }
      out.push(`<li>${inlineMd(ulItem[1] ?? '')}</li>`);
      continue;
    }

    const olItem = line.match(/^\d+[.)]\s+(.*)$/);
    if (olItem) {
      if (!inOl) {
        closeLists();
        out.push('<ol>');
        inOl = true;
      }
      out.push(`<li>${inlineMd(olItem[1] ?? '')}</li>`);
      continue;
    }

    if (line.trim() === '') {
      closeLists();
      continue;
    }

    closeLists();
    out.push(`<p>${inlineMd(line)}</p>`);
  }
  closeLists();
  if (inCode) out.push('</code></pre>');
  return out.join('\n');
}

// ─────────────────────────── 组件 ───────────────────────────

export default function ClassicReader() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { token } = theme.useToken();
  const isMobile = useIsMobile();
  const [tocOpen, setTocOpen] = useState(false);

  const [classic, setClassic] = useState<ClassicWithChapters | null>(null);
  const [chapter, setChapter] = useState<ChapterDetail | null>(null);
  const [activeChapterId, setActiveChapterId] = useState<string | null>(null);
  const [loadingBook, setLoadingBook] = useState(true);
  const [loadingChapter, setLoadingChapter] = useState(false);
  const [annotations, setAnnotations] = useState<ClassicAnnotation[]>([]);
  const [annotationCounts, setAnnotationCounts] = useState<Record<string, number>>({});

  const [activeTab, setActiveTab] = useState<CenterTab>('original');

  // 选区浮窗
  const [selMenu, setSelMenu] = useState<{
    x: number;
    y: number;
    info: SelectionInfo;
  } | null>(null);

  // 批注弹窗
  const [annoPopup, setAnnoPopup] = useState<{
    annotation: ClassicAnnotation;
    x: number;
    y: number;
  } | null>(null);
  const [editingAnnoId, setEditingAnnoId] = useState<string | null>(null);
  const [editingAnnoContent, setEditingAnnoContent] = useState('');

  // 新建批注弹窗
  const [createAnno, setCreateAnno] = useState<{
    info: SelectionInfo;
    x: number;
    y: number;
    content: string;
  } | null>(null);

  // AI 侧栏
  const [aiOpen, setAiOpen] = useState(false);
  const [aiContext, setAiContext] = useState<SelectionInfo | null>(null);
  const [aiQuestion, setAiQuestion] = useState('');
  const [aiAnswer, setAiAnswer] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const [qaHistory, setQaHistory] = useState<QAItem[]>([]);

  // 翻译
  const [translation, setTranslation] = useState<string>('');
  const [translating, setTranslating] = useState(false);
  const [editingTranslation, setEditingTranslation] = useState(false);
  const [translationDraft, setTranslationDraft] = useState('');

  // 学习心得
  const [notesContent, setNotesContent] = useState('');
  const [notesMap, setNotesMap] = useState<Record<string, string>>({});
  const [notesSaving, setNotesSaving] = useState(false);
  const [notesSummarizing, setNotesSummarizing] = useState(false);
  const notesTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const textContainerRef = useRef<HTMLDivElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  /** 将视口相对坐标转为阅读器容器相对坐标（用于 position:absolute 锚定） */
  const toContainerCoords = useCallback((rect: DOMRect): { x: number; y: number } => {
    const root = rootRef.current;
    if (!root) return { x: rect.left + rect.width / 2, y: rect.top };
    const rootRect = root.getBoundingClientRect();
    return {
      x: rect.left + rect.width / 2 - rootRect.left,
      y: rect.top - rootRect.top,
    };
  }, []);

  // 加载古籍
  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    (async () => {
      setLoadingBook(true);
      try {
        const data = await getClassic(id);
        if (cancelled) return;
        setClassic(data);
        if (data.chapters.length > 0) {
          setActiveChapterId(data.chapters[0]!.id);
        }
        // 加载心得
        try {
          const { items } = await getStudyNotes(id);
          if (cancelled) return;
          const map: Record<string, string> = {};
          for (const n of items) {
            if (n.chapter_id) map[n.chapter_id] = n.content;
          }
          setNotesMap(map);
        } catch {
          // ignore
        }
      } finally {
        if (!cancelled) setLoadingBook(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  // 加载章节
  useEffect(() => {
    if (!id || !activeChapterId) return;
    let cancelled = false;
    (async () => {
      setLoadingChapter(true);
      setSelMenu(null);
      setAnnoPopup(null);
      setCreateAnno(null);
      try {
        const data = await getChapter(id, activeChapterId);
        if (cancelled) return;
        setChapter(data);
        setAnnotations(data.annotations ?? []);
        setTranslation(data.translation ?? '');
        setEditingTranslation(false);
        setActiveTab('original');
        setNotesContent(notesMap[activeChapterId] ?? '');
      } finally {
        if (!cancelled) setLoadingChapter(false);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, activeChapterId]);

  // 切章时重置翻译/批注相关
  const switchChapter = (chapterId: string) => {
    setActiveChapterId(chapterId);
  };

  // 文本选区 → 浮窗
  const handleTextMouseUp = useCallback(() => {
    const container = textContainerRef.current;
    if (!container) return;
    const info = getSelectionOffsets(container);
    if (!info) {
      setSelMenu(null);
      return;
    }
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return;
    const rect = sel.getRangeAt(0).getBoundingClientRect();
    const { x, y } = toContainerCoords(rect);
    setSelMenu({ x, y, info });
  }, []);

  // 全局点击关闭浮窗
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      const target = e.target as HTMLElement | null;
      if (target?.closest('[data-float-menu]') || target?.closest('[data-anno-popup]') || target?.closest('[data-create-anno]')) {
        return;
      }
      setSelMenu(null);
      if (!target?.closest('[data-anno-popup]') && !target?.closest('.cls-mark')) {
        setAnnoPopup(null);
        setEditingAnnoId(null);
      }
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, []);

  // ── 选区菜单动作 ──
  const openAIForSelection = (info: SelectionInfo, presetQuestion?: string) => {
    setAiContext(info);
    setAiQuestion(presetQuestion ?? '');
    setAiAnswer('');
    setAiOpen(true);
    setSelMenu(null);
    setCreateAnno(null);
    clearSelection();
    if (presetQuestion) {
      // 自动发送预设翻译问题
      void doAsk(info, presetQuestion);
    }
  };

  const startCreateAnnotation = () => {
    if (!selMenu) return;
    setCreateAnno({ info: selMenu.info, x: selMenu.x, y: selMenu.y, content: '' });
    setSelMenu(null);
  };

  const doAsk = useCallback(
    async (info: SelectionInfo | null, questionOverride?: string) => {
      if (!id || !activeChapterId) return;
      const ctx = info ?? aiContext;
      const q = questionOverride ?? aiQuestion;
      if (!ctx || !q.trim()) {
        if (!q.trim()) message.warning('请输入问题');
        return;
      }
      setAiLoading(true);
      setAiAnswer('');
      try {
        const res = await askAI(id, activeChapterId, {
          selected_text: ctx.text,
          question: q,
        });
        setAiAnswer(res.answer);
        setQaHistory((prev) => [{ question: q, answer: res.answer }, ...prev].slice(0, 20));
      } catch {
        message.error('AI 问答失败');
      } finally {
        setAiLoading(false);
      }
    },
    [id, activeChapterId, aiContext, aiQuestion],
  );

  // ── 批注 CRUD ──
  const submitCreateAnnotation = async () => {
    if (!createAnno || !id || !activeChapterId) return;
    if (!createAnno.content.trim()) {
      message.warning('请输入批注内容');
      return;
    }
    try {
      const created = await createAnnotation(id, activeChapterId, {
        start_offset: createAnno.info.start,
        end_offset: createAnno.info.end,
        selected_text: createAnno.info.text,
        content: createAnno.content,
        note_type: 'annotation',
      });
      setAnnotations((prev) => [...prev, created]);
      setAnnotationCounts((prev) => ({
        ...prev,
        [activeChapterId]: (prev[activeChapterId] ?? 0) + 1,
      }));
      message.success('批注已添加');
      setCreateAnno(null);
      clearSelection();
    } catch {
      message.error('添加批注失败');
    }
  };

  const saveQAAsCard = async () => {
    if (!id || !activeChapterId || !aiContext || !aiAnswer) return;
    try {
      const created = await createAnnotation(id, activeChapterId, {
        start_offset: aiContext.start,
        end_offset: aiContext.end,
        selected_text: aiContext.text,
        content: `**问：** ${aiQuestion}\n\n**答：** ${aiAnswer}`,
        note_type: 'qa_card',
      });
      setAnnotations((prev) => [...prev, created]);
      setAnnotationCounts((prev) => ({
        ...prev,
        [activeChapterId]: (prev[activeChapterId] ?? 0) + 1,
      }));
      message.success('已存为问答卡片');
    } catch {
      message.error('保存失败');
    }
  };

  const startEditAnnotation = (a: ClassicAnnotation) => {
    setEditingAnnoId(a.id);
    setEditingAnnoContent(a.content);
  };

  const saveEditAnnotation = async () => {
    if (!editingAnnoId) return;
    const aid = editingAnnoId;
    const content = editingAnnoContent;
    setAnnotations((prev) =>
      prev.map((a) => (a.id === aid ? { ...a, content } : a)),
    );
    setEditingAnnoId(null);
    try {
      await updateAnnotation(aid, content);
      message.success('批注已更新');
    } catch {
      message.error('更新失败');
    }
  };

  const removeAnnotation = async (a: ClassicAnnotation) => {
    setAnnotations((prev) => prev.filter((x) => x.id !== a.id));
    setAnnoPopup(null);
    setEditingAnnoId(null);
    if (activeChapterId) {
      setAnnotationCounts((prev) => ({
        ...prev,
        [activeChapterId]: Math.max(0, (prev[activeChapterId] ?? 1) - 1),
      }));
    }
    try {
      await deleteAnnotation(a.id);
      message.success('批注已删除');
    } catch {
      message.error('删除失败');
    }
  };

  const onMarkClick = (e: React.MouseEvent, a: ClassicAnnotation) => {
    e.stopPropagation();
    setSelMenu(null);
    setCreateAnno(null);
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const { x, y } = toContainerCoords(rect);
    setAnnoPopup({
      annotation: a,
      x,
      y,
    });
    setEditingAnnoId(null);
  };

  // ── 翻译 ──
  const doTranslate = async () => {
    if (!id || !activeChapterId) return;
    setTranslating(true);
    try {
      const res = await translateChapter(id, activeChapterId);
      setTranslation(res.translation);
      setTranslationDraft(res.translation);
      message.success(`翻译已生成（${res.model_used}）`);
    } catch {
      message.error('翻译失败');
    } finally {
      setTranslating(false);
    }
  };

  const startEditTranslation = () => {
    setTranslationDraft(translation);
    setEditingTranslation(true);
  };

  const doSaveTranslation = async () => {
    if (!id || !activeChapterId) return;
    setEditingTranslation(false);
    setTranslation(translationDraft);
    try {
      await saveTranslation(id, activeChapterId, translationDraft);
      message.success('翻译已保存');
    } catch {
      message.error('保存失败');
    }
  };

  // ── 学习心得自动保存（2s 防抖） ──
  const onNotesChange = (val: string) => {
    setNotesContent(val);
    if (notesTimer.current) clearTimeout(notesTimer.current);
    notesTimer.current = setTimeout(async () => {
      if (!id || !activeChapterId) return;
      setNotesSaving(true);
      try {
        await saveStudyNotes(id, activeChapterId, val);
        setNotesMap((prev) => ({ ...prev, [activeChapterId]: val }));
      } catch {
        // ignore
      } finally {
        setNotesSaving(false);
      }
    }, 2000);
  };

  const doSummarize = async () => {
    if (!id || !activeChapterId) return;
    setNotesSummarizing(true);
    try {
      const res = await summarize(id, {
        chapter_id: activeChapterId,
        include_annotations: true,
        include_cards: true,
      });
      const merged = notesContent.trim()
        ? `${notesContent.trim()}\n\n---\n\n${res.summary_markdown}`
        : res.summary_markdown;
      setNotesContent(merged);
      // 立即保存
      await saveStudyNotes(id, activeChapterId, merged);
      setNotesMap((prev) => ({ ...prev, [activeChapterId]: merged }));
      message.success('AI 总结已生成并填入');
    } catch {
      message.error('总结生成失败');
    } finally {
      setNotesSummarizing(false);
    }
  };

  useEffect(() => {
    return () => {
      if (notesTimer.current) clearTimeout(notesTimer.current);
    };
  }, []);

  // 段切分
  const segments = useMemo(
    () => (chapter ? buildSegments(chapter.original_text, annotations) : []),
    [chapter, annotations],
  );

  const activeChapter =
    classic?.chapters.find((c) => c.id === activeChapterId) ?? null;

  if (loadingBook) return <Skeleton active paragraph={{ rows: 10 }} />;

  const inkBg = '#faf6ef';
  const inkBorder = '#e6dcc8';

  return (
    <div
      ref={rootRef}
      style={{
        display: 'flex',
        flexDirection: 'column',
        minHeight: 'calc(100vh - 140px)',
        position: 'relative',
      }}
    >
      <style>{`
        .cls-mark {
          cursor: pointer;
          border-radius: 3px;
          padding: 1px 1px;
          box-shadow: inset 0 -1px 0 rgba(0,0,0,0.04);
          transition: background .15s;
        }
        .cls-mark:hover { filter: brightness(0.95); }
        .cls-chapter-item {
          display: flex; align-items: center; gap: 8px;
          padding: 10px 12px; border-radius: 8px; cursor: pointer;
          font-size: 15px; transition: all .15s;
          border: 1px solid transparent;
        }
        .cls-chapter-item:hover { background: ${token.colorFillTertiary}; }
        .cls-chapter-item.is-active {
          background: linear-gradient(135deg, rgba(45,90,68,0.10), rgba(43,164,113,0.08));
          border-color: #2ba47155;
          color: #2d5a44; font-weight: 600;
        }
        .cls-classic-text p { margin: 0 0 1.1em; text-indent: 2em; line-height: 2.1; }
        .cls-classic-text { font-family: 'KaiTi','STKaiti','楷体','Songti SC',serif; }
        .cls-md-body h1,.cls-md-body h2,.cls-md-body h3 { line-height:1.4; margin:0.6em 0 0.4em; }
        .cls-md-body p { margin: 0 0 0.7em; line-height: 1.85; }
        .cls-md-body ul,.cls-md-body ol { margin: 0 0 0.7em; padding-left: 1.6em; }
        .cls-md-body li { margin-bottom: 0.3em; line-height: 1.7; }
        .cls-md-body pre { background: ${token.colorFillQuaternary}; padding:12px; border-radius:8px; overflow:auto; }
        .cls-md-body code { background: ${token.colorFillQuaternary}; padding:1px 5px; border-radius:4px; font-size:0.9em; }
        .cls-md-body pre code { background: transparent; padding:0; }
        .cls-float-btn {
          display: inline-flex; align-items: center; gap: 6px;
          white-space: nowrap; cursor: pointer; user-select: none;
          font-size: 14px; color: #fff;
          padding: 8px 14px; border-radius: 8px;
          transition: filter .15s, transform .1s;
        }
        .cls-float-btn:hover { filter: brightness(1.12); }
        .cls-float-btn:active { transform: scale(0.96); }
      `}</style>

      {/* 顶部栏 */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 14,
          gap: 12,
          flexWrap: 'wrap',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, minWidth: 0 }}>
          <Button
            icon={<ArrowLeftOutlined />}
            onClick={() => navigate('/classics')}
          >
            返回书柜
          </Button>
          {isMobile && (
            <Button icon={<ReadOutlined />} onClick={() => setTocOpen(true)}>
              目录
            </Button>
          )}
          <div style={{ minWidth: 0 }}>
            <Title level={4} className="cls-classic-text" style={{ margin: 0, lineHeight: 1.3 }}>
              {classic?.title}
            </Title>
            <Text type="secondary" style={{ fontSize: 14 }}>
              {classic?.dynasty} · {classic?.author}
            </Text>
          </div>
        </div>
      </div>

      {/* 主体三栏 */}
      <div style={{ display: 'flex', gap: 16, flex: 1, alignItems: 'flex-start' }}>
        {/* 左：章节目录 — 桌面端固定栏，手机端 Drawer */}
        {!isMobile && (
        <div
          style={{
            width: 220,
            flexShrink: 0,
            background: token.colorBgContainer,
            border: `1px solid ${token.colorBorderSecondary}`,
            borderRadius: 10,
            padding: 10,
            position: 'sticky',
            top: 8,
            maxHeight: 'calc(100vh - 160px)',
            overflow: 'auto',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: '4px 6px 10px',
              borderBottom: `1px solid ${token.colorBorderSecondary}`,
              marginBottom: 8,
            }}
          >
            <ReadOutlined style={{ color: '#b08d57' }} />
            <Text strong style={{ fontSize: 15 }}>
              章节目录
            </Text>
          </div>
          {classic && classic.chapters.length > 0 ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {classic.chapters.map((c) => (
                <div
                  key={c.id}
                  className={`cls-chapter-item${c.id === activeChapterId ? ' is-active' : ''}`}
                  onClick={() => switchChapter(c.id)}
                >
                  <span
                    style={{
                      flexShrink: 0,
                      width: 22,
                      height: 22,
                      borderRadius: '50%',
                      background:
                        c.id === activeChapterId ? '#2ba471' : token.colorFillTertiary,
                      color: c.id === activeChapterId ? '#fff' : token.colorTextSecondary,
                      fontSize: 12,
                      fontWeight: 600,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    {c.chapter_number}
                  </span>
                  <span
                    style={{
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                      flex: 1,
                    }}
                    title={c.title}
                  >
                    {c.title}
                  </span>
                  {annotationCounts[c.id] ? (
                    <Badge
                      count={annotationCounts[c.id]}
                      style={{ backgroundColor: '#b08d57' }}
                      size="small"
                    />
                  ) : null}
                </div>
              ))}
            </div>
          ) : (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="暂无章节"
              style={{ margin: '20px 0' }}
            />
          )}
        </div>
        )}

        {/* 中：阅读区 */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <Tabs
            activeKey={activeTab}
            onChange={(k) => setActiveTab(k as CenterTab)}
            items={[
              {
                key: 'original',
                label: (
                  <span>
                    <FileTextOutlined /> 原文
                  </span>
                ),
              },
              {
                key: 'translation',
                label: (
                  <span>
                    <TranslationOutlined /> 翻译
                  </span>
                ),
              },
              {
                key: 'notes',
                label: (
                  <span>
                    <EditOutlined /> 学习心得
                  </span>
                ),
              },
            ]}
            style={{ marginBottom: 4 }}
          />

          {loadingChapter ? (
            <Skeleton active paragraph={{ rows: 8 }} />
          ) : !chapter ? (
            <Empty description="请从左侧选择章节" />
          ) : activeTab === 'original' ? (
            <div
              ref={textContainerRef}
              className="cls-classic-text"
              onMouseUp={handleTextMouseUp}
              style={{
                background: inkBg,
                border: `1px solid ${inkBorder}`,
                borderRadius: 10,
                padding: '34px 40px 40px',
                maxWidth: 760,
                margin: '0 auto',
                fontSize: 18,
                color: '#2c2620',
                position: 'relative',
                boxShadow: '0 2px 12px rgba(60,40,20,0.06)',
                minHeight: 320,
              }}
            >
              {/* 装饰印章 */}
              <div
                style={{
                  position: 'absolute',
                  top: 18,
                  right: 22,
                  width: 34,
                  height: 34,
                  borderRadius: 6,
                  background: '#b94a3d',
                  color: '#fff',
                  fontFamily: "'KaiTi','楷体',serif",
                  fontSize: 18,
                  fontWeight: 700,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  boxShadow: '0 1px 3px rgba(0,0,0,0.18)',
                  opacity: 0.92,
                }}
                title={classic?.category}
              >
                经
              </div>
              <h2
                style={{
                  textAlign: 'center',
                  fontSize: 24,
                  fontWeight: 700,
                  marginBottom: 26,
                  color: '#3d2f22',
                  letterSpacing: '0.08em',
                }}
              >
                {chapter.title}
              </h2>
              <div style={{ position: 'relative' }}>
                {segments.length > 0 ? (
                  <p style={{ display: 'block' }}>
                    {segments.map((seg, idx) => {
                      const key = `${seg.start}-${seg.end}-${idx}`;
                      if (seg.annotations.length === 0) {
                        return (
                          <span key={key} style={{ whiteSpace: 'pre-wrap' }}>
                            {seg.text}
                          </span>
                        );
                      }
                      const top = seg.annotations[0]!;
                      return (
                        <span
                          key={key}
                          className="cls-mark"
                          style={{
                            background: highlightColor(seg.annotations),
                            whiteSpace: 'pre-wrap',
                          }}
                          onClick={(e) => onMarkClick(e, top)}
                          title={`${seg.annotations.length} 条${NOTE_TYPE_LABEL[top.note_type]}`}
                        >
                          {seg.text}
                          {seg.annotations.length > 1 ? (
                            <sup
                              style={{ color: '#b94a3d', fontWeight: 700, fontSize: 12 }}
                            >
                              {seg.annotations.length}
                            </sup>
                          ) : null}
                        </span>
                      );
                    })}
                  </p>
                ) : (
                  <Paragraph type="secondary" style={{ textAlign: 'center' }}>
                    本章暂无原文内容
                  </Paragraph>
                )}
              </div>

              {annotations.length === 0 && chapter.original_text ? (
                <div
                  style={{
                    marginTop: 28,
                    paddingTop: 16,
                    borderTop: `1px dashed ${inkBorder}`,
                    textAlign: 'center',
                    fontSize: 13,
                    color: '#9a8c78',
                  }}
                >
                  选中文字可进行 AI 问答 · 添加批注 · 翻译
                </div>
              ) : null}
            </div>
          ) : activeTab === 'translation' ? (
            <div
              style={{
                background: token.colorBgContainer,
                border: `1px solid ${token.colorBorderSecondary}`,
                borderRadius: 10,
                padding: '32px 36px',
                maxWidth: 760,
                margin: '0 auto',
                minHeight: 320,
              }}
            >
              <h2 style={{ textAlign: 'center', fontSize: 22, marginBottom: 24 }}>
                《{chapter.title}》白话译文
              </h2>
              {translating ? (
                <div style={{ textAlign: 'center', padding: 40 }}>
                  <Spin tip="正在翻译…" />
                </div>
              ) : translation && !editingTranslation ? (
                <div>
                  <div
                    className="cls-md-body"
                    style={{ fontSize: 17, lineHeight: 2, color: token.colorText }}
                    dangerouslySetInnerHTML={{ __html: renderMarkdown(translation) }}
                  />
                  <div
                    style={{
                      marginTop: 24,
                      paddingTop: 16,
                      borderTop: `1px dashed ${token.colorBorderSecondary}`,
                      display: 'flex',
                      gap: 12,
                      justifyContent: 'center',
                    }}
                  >
                    <Button icon={<EditOutlined />} onClick={startEditTranslation}>
                      编辑译文
                    </Button>
                  </div>
                </div>
              ) : translation && editingTranslation ? (
                <div>
                  <TextArea
                    value={translationDraft}
                    onChange={(e) => setTranslationDraft(e.target.value)}
                    autoSize={{ minRows: 8 }}
                    style={{ fontSize: 16 }}
                  />
                  <div
                    style={{
                      marginTop: 16,
                      display: 'flex',
                      gap: 12,
                      justifyContent: 'center',
                    }}
                  >
                    <Button
                      type="primary"
                      icon={<SaveOutlined />}
                      onClick={doSaveTranslation}
                    >
                      保存翻译
                    </Button>
                    <Button onClick={() => setEditingTranslation(false)}>取消</Button>
                  </div>
                </div>
              ) : (
                <div style={{ textAlign: 'center', padding: '40px 0' }}>
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description="本章暂无翻译"
                  />
                  <Button
                    type="primary"
                    icon={<TranslationOutlined />}
                    loading={translating}
                    onClick={doTranslate}
                    style={{ marginTop: 20 }}
                    size="large"
                  >
                    AI 一键翻译本章
                  </Button>
                </div>
              )}
            </div>
          ) : (
            /* 学习心得 */
            <div
              style={{
                background: token.colorBgContainer,
                border: `1px solid ${token.colorBorderSecondary}`,
                borderRadius: 10,
                padding: 20,
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  marginBottom: 14,
                  flexWrap: 'wrap',
                  gap: 10,
                }}
              >
                <Text strong style={{ fontSize: 16 }}>
                  <EditOutlined style={{ marginRight: 6 }} />
                  我的学习心得 · {activeChapter?.title ?? ''}
                </Text>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  {notesSaving ? (
                    <Text type="secondary" style={{ fontSize: 13 }}>
                      <Spin size="small" style={{ marginRight: 6 }} />
                      保存中…
                    </Text>
                  ) : (
                    <Text type="secondary" style={{ fontSize: 13 }}>
                      自动保存
                    </Text>
                  )}
                  <Button
                    icon={<ThunderboltOutlined />}
                    loading={notesSummarizing}
                    onClick={doSummarize}
                  >
                    从批注生成总结
                  </Button>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                <TextArea
                  value={notesContent}
                  onChange={(e) => onNotesChange(e.target.value)}
                  placeholder="记录你的读书心得、要点提炼、疑问思考……支持 Markdown 格式"
                  autoSize={{ minRows: 14 }}
                  style={{ flex: '1 1 320px', fontSize: 15, fontFamily: 'monospace' }}
                />
                <div
                  style={{
                    flex: '1 1 320px',
                    minHeight: 280,
                    padding: 16,
                    background: inkBg,
                    border: `1px solid ${inkBorder}`,
                    borderRadius: 8,
                    overflow: 'auto',
                  }}
                >
                  <Text type="secondary" style={{ fontSize: 13, display: 'block', marginBottom: 10 }}>
                    <BulbOutlined /> 实时预览
                  </Text>
                  {notesContent.trim() ? (
                    <div
                      className="cls-md-body"
                      style={{ fontSize: 15 }}
                      dangerouslySetInnerHTML={{ __html: renderMarkdown(notesContent) }}
                    />
                  ) : (
                    <Text type="secondary" style={{ fontSize: 14 }}>
                      预览区——输入内容后将实时渲染为格式化文本
                    </Text>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* 右：AI 问答侧栏 — 桌面端固定栏，手机端 Drawer */}
        {aiOpen && !isMobile ? (
          <div
            style={{
              width: 360,
              flexShrink: 0,
              background: token.colorBgContainer,
              border: `1px solid ${token.colorBorderSecondary}`,
              borderRadius: 10,
              display: 'flex',
              flexDirection: 'column',
              position: 'sticky',
              top: 8,
              maxHeight: 'calc(100vh - 160px)',
              boxShadow: '0 4px 16px rgba(40,30,20,0.08)',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '14px 16px',
                borderBottom: `1px solid ${token.colorBorderSecondary}`,
                background: 'linear-gradient(135deg, #2d5a44, #2ba471)',
                borderRadius: '10px 10px 0 0',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#fff' }}>
                <RobotOutlined style={{ fontSize: 18 }} />
                <Text style={{ color: '#fff', fontWeight: 600, fontSize: 16 }}>
                  AI 问答
                </Text>
              </div>
              <Button
                type="text"
                size="small"
                icon={<CloseOutlined style={{ color: '#fff' }} />}
                onClick={() => setAiOpen(false)}
              />
            </div>

            <div
              style={{
                flex: 1,
                overflow: 'auto',
                padding: 16,
                display: 'flex',
                flexDirection: 'column',
                gap: 14,
              }}
            >
              {/* 选中文字 */}
              {aiContext ? (
                <div
                  style={{
                    background: token.colorFillQuaternary,
                    borderLeft: '3px solid #b08d57',
                    borderRadius: 4,
                    padding: '10px 12px',
                  }}
                >
                  <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>
                    选中文字
                  </Text>
                  <Text style={{ fontSize: 15, color: token.colorText }}>"{aiContext.text}"</Text>
                </div>
              ) : (
                <div
                  style={{
                    background: token.colorFillQuaternary,
                    borderRadius: 6,
                    padding: '10px 12px',
                    fontSize: 14,
                    color: token.colorTextSecondary,
                  }}
                >
                  在左侧原文中选中文字后，可针对选段提问。
                </div>
              )}

              {/* 问题输入 */}
              <div>
                <Text type="secondary" style={{ fontSize: 13, display: 'block', marginBottom: 6 }}>
                  问题
                </Text>
                <TextArea
                  value={aiQuestion}
                  onChange={(e) => setAiQuestion(e.target.value)}
                  placeholder="请解释这段文字的含义…"
                  autoSize={{ minRows: 2, maxRows: 5 }}
                  style={{ fontSize: 15 }}
                />
              </div>
              <Button
                type="primary"
                icon={<RobotOutlined />}
                loading={aiLoading}
                block
                size="large"
                onClick={() => void doAsk(null)}
              >
                发送提问
              </Button>

              {/* AI 回答 */}
              {aiLoading ? (
                <div style={{ textAlign: 'center', padding: 20 }}>
                  <Spin tip="思考中…" />
                </div>
              ) : aiAnswer ? (
                <div>
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      marginBottom: 8,
                    }}
                  >
                    <Tag color="green" style={{ margin: 0 }}>
                      AI 回答
                    </Tag>
                  </div>
                  <div
                    className="cls-md-body"
                    style={{
                      background: inkBg,
                      border: `1px solid ${inkBorder}`,
                      borderRadius: 8,
                      padding: 14,
                      fontSize: 15,
                      lineHeight: 1.85,
                    }}
                    dangerouslySetInnerHTML={{ __html: renderMarkdown(aiAnswer) }}
                  />
                  {aiContext ? (
                    <Button
                      icon={<SaveOutlined />}
                      style={{ marginTop: 10 }}
                      block
                      onClick={saveQAAsCard}
                    >
                      存为问答卡片（高亮原文）
                    </Button>
                  ) : null}
                </div>
              ) : null}

              {/* 历史记录 */}
              {qaHistory.length > 0 ? (
                <div>
                  <div
                    style={{
                      borderTop: `1px dashed ${token.colorBorderSecondary}`,
                      paddingTop: 12,
                      marginTop: 4,
                    }}
                  >
                    <Text type="secondary" style={{ fontSize: 13 }}>
                      本次问答记录（{qaHistory.length}）
                    </Text>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 8 }}>
                    {qaHistory.map((item, idx) => (
                      <div
                        key={idx}
                        style={{
                          background: token.colorFillQuaternary,
                          borderRadius: 6,
                          padding: '8px 10px',
                          fontSize: 13,
                          cursor: 'pointer',
                        }}
                        onClick={() => {
                          setAiQuestion(item.question);
                          setAiAnswer(item.answer);
                        }}
                      >
                        <Text
                          style={{
                            display: 'block',
                            fontWeight: 500,
                            color: token.colorText,
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          Q：{item.question}
                        </Text>
                        <Text
                          type="secondary"
                          style={{
                            display: 'block',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                            marginTop: 2,
                          }}
                        >
                          A：{item.answer.replace(/[#*`]/g, '').slice(0, 40)}…
                        </Text>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        ) : (
          <Tooltip title="打开 AI 问答">
            <Button
              shape="circle"
              size="large"
              icon={<RobotOutlined />}
              onClick={() => setAiOpen(true)}
              style={{
                position: 'sticky',
                top: 8,
                backgroundColor: '#2ba471',
                borderColor: '#2ba471',
                color: '#fff',
                width: 48,
                height: 48,
                fontSize: 20,
              }}
            />
          </Tooltip>
        )}
      </div>

      {/* 选区浮窗菜单 */}
      {selMenu ? (
        <div
          data-float-menu
          style={{
            position: 'absolute',
            left: selMenu.x,
            top: selMenu.y - 52,
            transform: 'translateX(-50%)',
            display: 'flex',
            gap: 6,
            background: '#2c2620',
            padding: '6px 8px',
            borderRadius: 10,
            boxShadow: '0 8px 24px rgba(0,0,0,0.28)',
            zIndex: 1050,
          }}
        >
          <span
            className="cls-float-btn"
            style={{ background: '#2ba471' }}
            onClick={() => openAIForSelection(selMenu.info)}
          >
            <RobotOutlined /> AI 问答
          </span>
          <span
            className="cls-float-btn"
            style={{ background: '#b08d57' }}
            onClick={startCreateAnnotation}
          >
            <EditOutlined /> 添加批注
          </span>
          <span
            className="cls-float-btn"
            style={{ background: '#5b7a9c' }}
            onClick={() =>
              openAIForSelection(selMenu.info, '请将这段古文翻译为通顺易懂的白话文，并简要解释其中医理。')
            }
          >
            <TranslationOutlined /> 翻译选中
          </span>
          {/* 小三角 */}
          <div
            style={{
              position: 'absolute',
              left: '50%',
              bottom: -6,
              transform: 'translateX(-50%) rotate(45deg)',
              width: 12,
              height: 12,
              background: '#2c2620',
            }}
          />
        </div>
      ) : null}

      {/* 新建批注浮窗 */}
      {createAnno ? (
        <div
          data-create-anno
          style={{
            position: 'absolute',
            left: createAnno.x,
            top: createAnno.y - 8,
            transform: 'translate(-50%, -100%)',
            width: 320,
            background: token.colorBgContainer,
            border: `1px solid ${token.colorBorderSecondary}`,
            borderRadius: 10,
            padding: 14,
            boxShadow: '0 8px 24px rgba(0,0,0,0.18)',
            zIndex: 1050,
          }}
        >
          <div
            style={{
              background: token.colorFillQuaternary,
              borderLeft: '3px solid #b08d57',
              borderRadius: 4,
              padding: '6px 10px',
              marginBottom: 10,
              fontSize: 14,
              color: token.colorTextSecondary,
            }}
          >
            "{createAnno.info.text}"
          </div>
          <TextArea
            value={createAnno.content}
            onChange={(e) => setCreateAnno({ ...createAnno, content: e.target.value })}
            placeholder="写下你的批注、理解或疑问…"
            autoSize={{ minRows: 3, maxRows: 6 }}
            autoFocus
            style={{ fontSize: 15 }}
          />
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 10 }}>
            <Button size="small" onClick={() => setCreateAnno(null)}>
              取消
            </Button>
            <Button type="primary" size="small" icon={<SaveOutlined />} onClick={submitCreateAnnotation}>
              保存批注
            </Button>
          </div>
        </div>
      ) : null}

      {/* 批注详情/编辑弹窗 */}
      {annoPopup ? (
        <div
          data-anno-popup
          style={{
            position: 'absolute',
            left: annoPopup.x,
            top: annoPopup.y - 8,
            transform: 'translate(-50%, -100%)',
            width: 340,
            background: token.colorBgContainer,
            border: `1px solid ${token.colorBorderSecondary}`,
            borderRadius: 10,
            padding: 14,
            boxShadow: '0 8px 24px rgba(0,0,0,0.18)',
            zIndex: 1050,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <Tag color="gold" style={{ margin: 0 }}>
              {NOTE_TYPE_LABEL[annoPopup.annotation.note_type] ?? '批注'}
            </Tag>
            <Text
              type="secondary"
              style={{ fontSize: 12, marginLeft: 'auto' }}
            >
              {annoPopup.annotation.created_at
                ? new Date(annoPopup.annotation.created_at).toLocaleString('zh-CN', {
                    month: '2-digit',
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit',
                  })
                : ''}
            </Text>
          </div>
          <div
            style={{
              background: token.colorFillQuaternary,
              borderRadius: 4,
              padding: '5px 10px',
              marginBottom: 10,
              fontSize: 13,
              color: token.colorTextSecondary,
              borderLeft: '3px solid #b08d57',
            }}
          >
            "{annoPopup.annotation.selected_text}"
          </div>
          {editingAnnoId === annoPopup.annotation.id ? (
            <div>
              <TextArea
                value={editingAnnoContent}
                onChange={(e) => setEditingAnnoContent(e.target.value)}
                autoSize={{ minRows: 3, maxRows: 6 }}
                autoFocus
                style={{ fontSize: 15 }}
              />
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 10 }}>
                <Button size="small" onClick={() => setEditingAnnoId(null)}>
                  取消
                </Button>
                <Button type="primary" size="small" icon={<SaveOutlined />} onClick={saveEditAnnotation}>
                  保存
                </Button>
              </div>
            </div>
          ) : (
            <div>
              <div
                className="cls-md-body"
                style={{ fontSize: 15, maxHeight: 200, overflow: 'auto', lineHeight: 1.8 }}
                dangerouslySetInnerHTML={{
                  __html: renderMarkdown(annoPopup.annotation.content),
                }}
              />
              <div
                style={{
                  display: 'flex',
                  gap: 8,
                  justifyContent: 'flex-end',
                  marginTop: 12,
                  paddingTop: 10,
                  borderTop: `1px dashed ${token.colorBorderSecondary}`,
                }}
              >
                <Button
                  size="small"
                  icon={<EditOutlined />}
                  onClick={() => startEditAnnotation(annoPopup.annotation)}
                >
                  编辑
                </Button>
                <Button
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={() => removeAnnotation(annoPopup.annotation)}
                >
                  删除
                </Button>
              </div>
            </div>
          )}
        </div>
      ) : null}

      {/* 手机端章节目录 Drawer */}
      <Drawer
        title="章节目录"
        open={isMobile && tocOpen}
        onClose={() => setTocOpen(false)}
        placement="left"
        width={260}
        styles={{ body: { padding: 8 } }}
      >
        {classic && classic.chapters.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {classic.chapters.map((c) => (
              <div
                key={c.id}
                className={`cls-chapter-item${c.id === activeChapterId ? ' is-active' : ''}`}
                onClick={() => { switchChapter(c.id); setTocOpen(false); }}
              >
                <span
                  style={{
                    flexShrink: 0,
                    width: 22,
                    height: 22,
                    borderRadius: '50%',
                    background: c.id === activeChapterId ? '#2ba471' : token.colorFillTertiary,
                    color: c.id === activeChapterId ? '#fff' : token.colorTextSecondary,
                    fontSize: 12,
                    fontWeight: 600,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  {c.chapter_number}
                </span>
                <span
                  style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}
                  title={c.title}
                >
                  {c.title}
                </span>
                {annotationCounts[c.id] ? (
                  <Badge count={annotationCounts[c.id]} style={{ backgroundColor: '#b08d57' }} size="small" />
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无章节" />
        )}
      </Drawer>

      {/* 手机端 AI 问答 Drawer */}
      {aiOpen && isMobile && (
        <Drawer
          title={<span style={{ color: '#fff' }}><RobotOutlined /> AI 问答</span>}
          open={aiOpen && isMobile}
          onClose={() => setAiOpen(false)}
          placement="bottom"
          height="70%"
          styles={{ header: { background: 'linear-gradient(135deg, #2d5a44, #2ba471)' } }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14, height: '100%', overflow: 'auto' }}>
            {aiContext ? (
              <div style={{ background: token.colorFillQuaternary, borderLeft: '3px solid #b08d57', borderRadius: 4, padding: '10px 12px' }}>
                <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 4 }}>选中文字</Text>
                <Text style={{ fontSize: 14 }}>{aiContext.text}</Text>
              </div>
            ) : null}
            <TextArea
              value={aiQuestion}
              onChange={(e) => setAiQuestion(e.target.value)}
              placeholder="请输入你的问题…"
              autoSize={{ minRows: 2 }}
            />
            <Button type="primary" icon={<ThunderboltOutlined />} loading={aiLoading} onClick={() => doAsk(null)} block>
              提问
            </Button>
            {aiAnswer && (
              <div className="cls-md-body" style={{ fontSize: 15, lineHeight: 1.8 }} dangerouslySetInnerHTML={{ __html: renderMarkdown(aiAnswer) }} />
            )}
            {qaHistory.length > 0 && (
              <div>
                <Text type="secondary" style={{ fontSize: 13, display: 'block', marginBottom: 8 }}>历史问答</Text>
                {qaHistory.slice(-5).reverse().map((qa, i) => (
                  <div key={i} style={{ marginBottom: 10, padding: 8, background: token.colorFillQuaternary, borderRadius: 6 }}>
                    <Text strong style={{ fontSize: 14 }}>Q: {qa.question}</Text>
                    <div className="cls-md-body" style={{ fontSize: 14, marginTop: 4 }} dangerouslySetInnerHTML={{ __html: renderMarkdown(qa.answer) }} />
                  </div>
                ))}
              </div>
            )}
          </div>
        </Drawer>
      )}
    </div>
  );
}
