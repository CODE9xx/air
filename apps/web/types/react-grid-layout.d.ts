declare module 'react-grid-layout' {
  import type { ComponentType } from 'react';

  export type Layout = {
    i: string;
    x: number;
    y: number;
    w: number;
    h: number;
    minW?: number;
    minH?: number;
    maxW?: number;
    maxH?: number;
    static?: boolean;
  };

  export const Responsive: ComponentType<any>;
  export function WidthProvider<T>(component: T): ComponentType<any>;
}
