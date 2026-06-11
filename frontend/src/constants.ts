export const DRUG_STATUS_COLOR: Record<string, string> = {
  充足: 'green',
  低库存: 'orange',
  已过期: 'red',
};

export const REMINDER_STATUS_COLOR: Record<string, string> = {
  待服: 'blue',
  已服: 'green',
  漏服: 'red',
};

export const HERB_NATURE_COLOR: Record<string, string> = {
  寒: 'blue',
  凉: 'cyan',
  平: 'default',
  温: 'orange',
  热: 'red',
};

export const TOXICITY_COLOR: Record<string, string> = {
  无毒: 'green',
  小毒: 'gold',
  有毒: 'orange',
  大毒: 'red',
};

export const PAGE_SIZE = 20;

export const DATE_FORMAT = 'YYYY-MM-DD HH:mm';
