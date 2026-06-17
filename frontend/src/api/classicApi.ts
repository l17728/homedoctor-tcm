import { request } from './client';

/** 经典古籍 */
export interface Classic {
  id: string;
  title: string;
  author: string;
  dynasty: string;
  category: string;
  description: string;
  cover_color: string;
  total_chapters: number;
}

/** 章节摘要（目录项） */
export interface ClassicChapterSummary {
  id: string;
  chapter_number: number;
  title: string;
}

/** 含章节列表的古籍 */
export interface ClassicWithChapters extends Classic {
  chapters: ClassicChapterSummary[];
}

/** 批注类型：annotation=批注 / qa_card=问答卡片 / translation_note=译注 */
export type AnnotationNoteType = 'annotation' | 'qa_card' | 'translation_note';

/** 批注 */
export interface ClassicAnnotation {
  id: string;
  start_offset: number;
  end_offset: number;
  selected_text: string;
  content: string;
  note_type: AnnotationNoteType;
  created_at?: string;
  updated_at?: string;
}

/** 章节详情 */
export interface ChapterDetail {
  id: string;
  chapter_number: number;
  title: string;
  original_text: string;
  translation?: string;
  translator_notes?: string;
  annotations: ClassicAnnotation[];
}

/** 学习心得 */
export interface StudyNote {
  id: string;
  chapter_id?: string;
  content: string;
  created_at?: string;
  updated_at?: string;
}

// ─────────────────────────── Mock 数据（后端不可用时降级） ───────────────────────────

const NEIJING_OPENING = `昔在黄帝，生于神农氏，长而敦敏，成而登天。

乃问于天师曰：余闻上古之人，春秋皆度百岁，而动作不衰；今时之人，年半百而动作皆衰者，时世异耶？人将失之耶？

岐伯对曰：上古之人，其知道者，法于阴阳，和于术数，食饮有节，起居有常，不妄作劳，故能形与神俱，而尽终其天年，度百岁乃去。

今时之人不然也，以酒为浆，以妄为常，醉以入房，以欲竭其精，以耗散其真，不知持满，不时御神，务快其心，逆于生乐，起居无节，故半百而衰也。

夫上古圣人之教下也，皆谓之虚邪贼风，避之有时，恬淡虚无，真气从之，精神内守，病安从来。

是以志闲而少欲，心安而不惧，形劳而不倦，气从以顺，各从其欲，皆得所愿。

故美其食，任其服，乐其俗，高下不相慕，其民故曰朴。

是以嗜欲不能劳其目，淫邪不能惑其心，愚智贤不肖不惧于物，故合于道。

所以能年皆度百岁而动作不衰者，以其德全不危也。`;

const NEIJING_CH2 = `黄帝曰：人年老而无子者，材力尽耶？将天数然也？

岐伯曰：女子七岁，肾气盛，齿更发长。二七而天癸至，任脉通，太冲脉盛，月事以时下，故有子。

三七，肾气平均，故真牙生而长极。四七，筋骨坚，发长极，身体盛壮。

五七，阳明脉衰，面始焦，发始堕。六七，三阳脉衰于上，面皆焦，发始白。

七七，任脉虚，太冲脉衰少，天癸竭，地道不通，故形坏而无子也。

丈夫八岁，肾气实，发长齿更。二八，肾气盛，天癸至，精气溢泻，阴阳和，故能有子。

三八，肾气平均，筋骨劲强，故真牙生而长极。四八，筋骨隆盛，肌肉满壮。

五八，肾气衰，发堕齿槁。六八，阳气衰竭于上，面焦，发鬓颁白。

七八，肝气衰，筋不能动，天癸竭，精少，肾脏衰，形体皆极。八八，则齿发去。`;

const MOCK_CLASSICS: Classic[] = [
  {
    id: 'c1',
    title: '黄帝内经·素问',
    author: '佚名（岐黄）',
    dynasty: '先秦至汉',
    category: '医经',
    description: '中医理论奠基之作，以黄帝与岐伯问答形式阐述阴阳五行、藏象经络、病因病机、养生防病之道。',
    cover_color: '#2d5a44',
    total_chapters: 81,
  },
  {
    id: 'c2',
    title: '黄帝内经·灵枢',
    author: '佚名（岐黄）',
    dynasty: '先秦至汉',
    category: '医经',
    description: '又称《针经》，详论经脉、穴位、刺法，是针灸学的理论渊源，与《素问》互为表里。',
    cover_color: '#1f5a52',
    total_chapters: 81,
  },
  {
    id: 'c3',
    title: '伤寒论',
    author: '张仲景',
    dynasty: '东汉',
    category: '伤寒',
    description: '确立六经辨证体系，载方一百一十三首，被尊为"方书之祖"，外感病辨证论治之圭臬。',
    cover_color: '#274c6e',
    total_chapters: 22,
  },
  {
    id: 'c4',
    title: '金匮要略',
    author: '张仲景',
    dynasty: '东汉',
    category: '伤寒',
    description: '论述杂病证治，以内科杂病为主，兼及妇科、外科，载方二百零五首，方证对应精当。',
    cover_color: '#3a4a66',
    total_chapters: 25,
  },
  {
    id: 'c5',
    title: '温病条辨',
    author: '吴鞠通',
    dynasty: '清',
    category: '温病',
    description: '创立三焦辨证，系统论述温病的病因、传变与治法，集温病学派之大成。',
    cover_color: '#8a3a44',
    total_chapters: 6,
  },
  {
    id: 'c6',
    title: '温热论',
    author: '叶天士',
    dynasty: '清',
    category: '温病',
    description: '温病学派开山之作，提出"温邪上受，首先犯肺，逆传心包"的著名论断，创卫气营血辨证。',
    cover_color: '#9c4a4a',
    total_chapters: 4,
  },
  {
    id: 'c7',
    title: '汤头歌诀',
    author: '汪昂',
    dynasty: '清',
    category: '方书',
    description: '以歌诀形式收录常用方剂三百余首，便于记诵，初学方剂之捷径，流传极广。',
    cover_color: '#6e4a2e',
    total_chapters: 20,
  },
  {
    id: 'c8',
    title: '本草纲目',
    author: '李时珍',
    dynasty: '明',
    category: '方书',
    description: '集本草学之大成，收载药物一千八百九十二种，附方一万一千余首，被誉为"东方药学巨典"。',
    cover_color: '#5a6e2e',
    total_chapters: 52,
  },
];

const MOCK_CHAPTERS: Record<string, { id: string; chapter_number: number; title: string; original_text: string }[]> = {
  c1: [
    { id: 'c1-1', chapter_number: 1, title: '上古天真论篇第一', original_text: NEIJING_OPENING },
    { id: 'c1-2', chapter_number: 2, title: '生气通天论篇第三', original_text: NEIJING_CH2 },
    { id: 'c1-3', chapter_number: 3, title: '阴阳应象大论篇第五', original_text: '黄帝曰：阴阳者，天地之道也，万物之纲纪，变化之父母，生杀之本始，神明之府也。\n\n治病必求于本。故积阳为天，积阴为地。阴静阳躁，阳生阴长，阳杀阴藏。' },
  ],
};

const mockChaptersFor = (classicId: string): { id: string; chapter_number: number; title: string; original_text: string }[] => {
  if (MOCK_CHAPTERS[classicId]) return MOCK_CHAPTERS[classicId]!;
  return Array.from({ length: 3 }, (_, i) => ({
    id: `${classicId}-${i + 1}`,
    chapter_number: i + 1,
    title: `第${['一', '二', '三'][i] ?? (i + 1)}篇`,
    original_text: '（本章节原文尚在整理之中……）',
  }));
};

// ─────────────────────────── API 函数 ───────────────────────────

export async function getClassics(): Promise<{ items: Classic[] }> {
  try {
    return await request<{ items: Classic[] }>('/api/classics');
  } catch {
    return { items: MOCK_CLASSICS };
  }
}

export async function getClassic(id: string): Promise<ClassicWithChapters> {
  try {
    const data = await request<Classic & { chapters: ClassicChapterSummary[] }>(
      `/api/classics/${id}`,
    );
    return { ...data, chapters: data.chapters ?? [] };
  } catch {
    const found = MOCK_CLASSICS.find((c) => c.id === id);
    const base = found ?? MOCK_CLASSICS[0]!;
    const chapters = mockChaptersFor(id).map((c) => ({
      id: c.id,
      chapter_number: c.chapter_number,
      title: c.title,
    }));
    return { ...base, id, chapters };
  }
}

export async function getChapter(
  classicId: string,
  chapterId: string,
): Promise<ChapterDetail> {
  try {
    const data = await request<ChapterDetail & { annotations?: ClassicAnnotation[] }>(
      `/api/classics/${classicId}/chapters/${chapterId}`,
    );
    return { ...data, annotations: data.annotations ?? [] };
  } catch {
    const chs = mockChaptersFor(classicId);
    const ch = chs.find((c) => c.id === chapterId) ?? chs[0]!;
    return {
      id: ch.id,
      chapter_number: ch.chapter_number,
      title: ch.title,
      original_text: ch.original_text,
      translation: undefined,
      annotations: [],
    };
  }
}

export async function getChapterAnnotations(
  classicId: string,
  chapterId: string,
): Promise<{ items: ClassicAnnotation[] }> {
  try {
    return await request<{ items: ClassicAnnotation[] }>(
      `/api/classics/${classicId}/chapters/${chapterId}/annotations`,
    );
  } catch {
    return { items: [] };
  }
}

export async function createAnnotation(
  classicId: string,
  chapterId: string,
  body: { start_offset: number; end_offset: number; selected_text: string; content: string; note_type: AnnotationNoteType },
): Promise<ClassicAnnotation> {
  try {
    return await request<ClassicAnnotation>(
      `/api/classics/${classicId}/chapters/${chapterId}/annotations`,
      { method: 'POST', body: JSON.stringify(body) },
    );
  } catch {
    return {
      id: `a_${Date.now()}`,
      ...body,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
  }
}

export async function updateAnnotation(
  annotationId: string,
  content: string,
): Promise<void> {
  try {
    await request<void>(`/api/classics/annotations/${annotationId}`, {
      method: 'PUT',
      body: JSON.stringify({ content }),
    });
  } catch {
    // mock: no-op
  }
}

export async function deleteAnnotation(annotationId: string): Promise<void> {
  try {
    await request<void>(`/api/classics/annotations/${annotationId}`, {
      method: 'DELETE',
    });
  } catch {
    // mock: no-op
  }
}

export async function askAI(
  classicId: string,
  chapterId: string,
  body: { selected_text: string; question: string },
): Promise<{ answer: string; model_used: string }> {
  try {
    return await request<{ answer: string; model_used: string }>(
      `/api/classics/${classicId}/chapters/${chapterId}/ask`,
      { method: 'POST', body: JSON.stringify(body) },
    );
  } catch {
    return {
      answer:
        '（当前为离线示例）AI 问答功能需要连接后端大语言模型。\n\n您选中的文字是：\n\n> ' +
        body.selected_text +
        '\n\n请确保后端服务已启动，即可获得详尽的中医典籍解读。',
      model_used: 'mock',
    };
  }
}

export async function translateChapter(
  classicId: string,
  chapterId: string,
): Promise<{ translation: string; model_used: string }> {
  try {
    return await request<{ translation: string; model_used: string }>(
      `/api/classics/${classicId}/chapters/${chapterId}/translate`,
      { method: 'POST', body: JSON.stringify({}) },
    );
  } catch {
    return {
      translation: '（离线示例）白话翻译功能需连接后端 AI 服务。原文大意请参考右侧 AI 问答。',
      model_used: 'mock',
    };
  }
}

export async function saveTranslation(
  classicId: string,
  chapterId: string,
  translation: string,
): Promise<void> {
  try {
    await request<void>(`/api/classics/${classicId}/chapters/${chapterId}/translation`, {
      method: 'PUT',
      body: JSON.stringify({ translation }),
    });
  } catch {
    // mock: no-op
  }
}

export async function getStudyNotes(
  classicId: string,
): Promise<{ items: StudyNote[] }> {
  try {
    return await request<{ items: StudyNote[] }>(`/api/classics/${classicId}/study-notes`);
  } catch {
    return { items: [] };
  }
}

export async function saveStudyNotes(
  classicId: string,
  chapterId: string,
  content: string,
): Promise<void> {
  try {
    await request<void>(`/api/classics/${classicId}/chapters/${chapterId}/study-notes`, {
      method: 'PUT',
      body: JSON.stringify({ content }),
    });
  } catch {
    // mock: no-op
  }
}

export async function summarize(
  classicId: string,
  body: { chapter_id?: string; include_annotations: boolean; include_cards: boolean },
): Promise<{ summary_markdown: string }> {
  try {
    return await request<{ summary_markdown: string }>(`/api/classics/${classicId}/summarize`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  } catch {
    return {
      summary_markdown:
        '## 章节总结\n\n（离线示例）AI 总结功能需连接后端服务。\n\n请确保后端已启动，即可自动生成本章的要点提炼、批注归纳与学习卡片汇总。',
    };
  }
}
