import { Alert, Button, Collapse, Form, Skeleton } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { getSchema, type SchemaDefinition, type SchemaFieldDef } from '../api/schemaApi';
import SchemaField from './SchemaField';

export interface SchemaFormProps {
  schemaType: string;
  initialValues?: Record<string, unknown>;
  onSubmit: (values: Record<string, unknown>) => void;
  layout?: 'horizontal' | 'vertical' | 'inline';
  disabled?: boolean;
}

/** Group name → ordered list of fields. */
type GroupedFields = Map<string, SchemaFieldDef[]>;

/**
 * Auto-render a full form from a backend schema definition.
 *
 * 1. Fetches the schema for `schemaType` from `/api/schemas/{schemaType}`.
 * 2. Groups fields by `field.group` into collapsible panels.
 * 3. Renders each field using `<SchemaField />`.
 * 4. Validates and submits via AntD Form.
 */
export default function SchemaForm({
  schemaType,
  initialValues,
  onSubmit,
  layout = 'vertical',
  disabled = false,
}: SchemaFormProps) {
  const [form] = Form.useForm();
  const [schema, setSchema] = useState<SchemaDefinition | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    getSchema(schemaType)
      .then(setSchema)
      .catch(() => setError('加载架构定义失败'))
      .finally(() => setLoading(false));
  }, [schemaType]);

  /** Group fields by `field.group`, sorted by `field.order` within each group. */
  const grouped: GroupedFields = useMemo(() => {
    const groups: GroupedFields = new Map();
    if (!schema) return groups;
    for (const field of schema.fields) {
      const groupName = field.group ?? '默认分组';
      const arr = groups.get(groupName);
      if (arr) {
        arr.push(field);
      } else {
        groups.set(groupName, [field]);
      }
    }
    for (const fields of groups.values()) {
      fields.sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
    }
    return groups;
  }, [schema]);

  const handleFinish = (values: Record<string, unknown>) => {
    onSubmit(values);
  };

  if (loading) return <Skeleton active />;
  if (error) return <Alert type="error" message={error} />;
  if (!schema || schema.fields.length === 0) return null;

  const groupEntries = Array.from(grouped.entries());
  const allGroupKeys = groupEntries.map(([key]) => key);

  return (
    <Form
      form={form}
      layout={layout}
      initialValues={initialValues}
      onFinish={handleFinish}
    >
      <Collapse
        defaultActiveKey={allGroupKeys}
        items={groupEntries.map(([groupName, fields]) => ({
          key: groupName,
          label: groupName,
          children: fields.map((field) => (
            <SchemaField
              key={field.id}
              field={field}
              value={undefined}
              onChange={() => {}}
              disabled={disabled}
            />
          )),
        }))}
      />

      {!disabled && (
        <Form.Item style={{ marginTop: 24, marginBottom: 0 }}>
          <Button type="primary" htmlType="submit">
            提交
          </Button>
        </Form.Item>
      )}
    </Form>
  );
}
