import { Tag } from 'antd';

interface StatusTagProps {
  status: string;
  colorMap: Record<string, string>;
}

export default function StatusTag({ status, colorMap }: StatusTagProps) {
  const color = colorMap[status] ?? 'default';
  return <Tag color={color}>{status}</Tag>;
}
