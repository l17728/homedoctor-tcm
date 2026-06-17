import { DatePicker, Form, Input, InputNumber, Select, Switch } from 'antd';
import type { Rule } from 'antd/es/form';
import dayjs from 'dayjs';
import type { Dayjs } from 'dayjs';
import type { SchemaFieldDef } from '../api/schemaApi';

export type { SchemaFieldDef } from '../api/schemaApi';

export interface SchemaFieldProps {
  field: SchemaFieldDef;
  value: unknown;
  onChange: (value: unknown) => void;
  disabled?: boolean;
}

/**
 * Extra props for Form.Item when the field type requires value transformation.
 * - date fields store YYYY-MM-DD strings but DatePicker expects Dayjs objects.
 */
interface FormItemExtra {
  getValueProps?: (value: unknown) => { value: Dayjs | null };
  getValueFromEvent?: (date: Dayjs | null) => string | undefined;
}

/**
 * Auto-render a single form field from a SchemaFieldDef.
 *
 * The AntD control is chosen based on `field.type`:
 * - string  → <Input />
 * - number  → <InputNumber />
 * - text    → <Input.TextArea />
 * - enum    → <Select /> with options from enumValues
 * - boolean → <Switch />
 * - date    → <DatePicker /> (stores YYYY-MM-DD, displays via dayjs)
 *
 * When placed inside an AntD <Form>, the Form.Item manages value/onChange
 * via cloneElement. The `value`/`onChange` props are used for standalone
 * (controlled) mode outside of a Form.
 */
export default function SchemaField({
  field,
  value,
  onChange,
  disabled = false,
}: SchemaFieldProps) {
  const rules: Rule[] = [];
  if (field.required) {
    rules.push({ required: true, message: `请输入${field.label}` });
  }

  // Date fields need getValueProps/getValueFromEvent to convert between
  // string storage (YYYY-MM-DD) and Dayjs objects expected by DatePicker.
  const formItemExtra: FormItemExtra = {};
  if (field.type === 'date') {
    formItemExtra.getValueProps = (val: unknown) => ({
      value: typeof val === 'string' && val ? dayjs(val) : null,
    });
    formItemExtra.getValueFromEvent = (date: Dayjs | null) =>
      date ? date.format('YYYY-MM-DD') : undefined;
  }

  // ---- Render the correct AntD control per field type -------------
  let control: React.ReactNode;
  switch (field.type) {
    case 'number':
      control = (
        <InputNumber
          value={value as number | null | undefined}
          onChange={(v) => onChange(v ?? null)}
          disabled={disabled}
          style={{ width: '100%' }}
        />
      );
      break;

    case 'text':
      control = (
        <Input.TextArea
          value={(value as string | undefined) ?? ''}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          autoSize={{ minRows: 2, maxRows: 6 }}
        />
      );
      break;

    case 'enum':
      control = (
        <Select
          value={(value as string | undefined) ?? undefined}
          onChange={(v) => onChange(v)}
          disabled={disabled}
          allowClear={!field.required}
          placeholder={`请选择${field.label}`}
          options={(field.enumValues ?? []).map((v) => ({
            label: v,
            value: v,
          }))}
        />
      );
      break;

    case 'boolean':
      control = (
        <Switch
          checked={Boolean(value)}
          onChange={(checked) => onChange(checked)}
          disabled={disabled}
        />
      );
      break;

    case 'date':
      control = (
        <DatePicker disabled={disabled} style={{ width: '100%' }} />
      );
      break;

    case 'string':
    default:
      control = (
        <Input
          value={(value as string | undefined) ?? ''}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          placeholder={`请输入${field.label}`}
        />
      );
      break;
  }

  return (
    <Form.Item
      label={field.label}
      name={field.name}
      rules={rules}
      getValueProps={formItemExtra.getValueProps}
      getValueFromEvent={formItemExtra.getValueFromEvent}
    >
      {control}
    </Form.Item>
  );
}
