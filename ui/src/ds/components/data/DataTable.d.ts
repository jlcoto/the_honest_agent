export interface DataColumn { key: string; label: string; align?: 'left' | 'right' | 'center'; mono?: boolean; width?: number | string; render?: (row: any) => React.ReactNode; }
export interface DataTableProps {
  columns: DataColumn[];
  rows: any[];
  dense?: boolean;
  rowKey?: string;
  onRowClick?: (row: any) => void;
}
export declare function DataTable(props: DataTableProps): JSX.Element;
