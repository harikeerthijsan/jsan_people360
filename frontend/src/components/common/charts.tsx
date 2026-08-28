'use client';

import * as React from 'react';

import { cn } from '@/lib/utils';

/**
 * Small, dependency-free SVG charts for dashboards.
 *
 * Colours come from CSS variables (`--primary`, `--chart-*` when present) so
 * the charts follow the theme, and every chart also renders its figures as
 * text — a bar or an arc alone cannot be read precisely, and a screen reader
 * cannot read it at all.
 */

export interface ChartPoint {
  label: string;
  value: number;
  /** Explicit colour for this point; falls back to the palette by index. */
  color?: string;
}

const PALETTE = [
  'var(--chart-1, hsl(221 83% 53%))',
  'var(--chart-2, hsl(142 71% 45%))',
  'var(--chart-3, hsl(38 92% 50%))',
  'var(--chart-4, hsl(0 84% 60%))',
  'var(--chart-5, hsl(262 83% 58%))',
  'var(--chart-6, hsl(190 90% 40%))',
];

export function chartColor(index: number): string {
  return PALETTE[index % PALETTE.length] ?? 'var(--primary)';
}

function niceMax(values: number[]): number {
  const max = Math.max(0, ...values);
  if (max === 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(max));
  const step = magnitude / 2;
  return Math.ceil(max / step) * step;
}

interface BarChartProps {
  data: ChartPoint[];
  height?: number;
  color?: string;
  /** Show the value above every bar. */
  valueLabels?: boolean;
  /** How a value is written above its bar, e.g. with thousands separators. */
  formatValue?: (value: number) => string;
  className?: string;
  ariaLabel: string;
}

/** Vertical bars, one per point, with a light horizontal grid. */
export function BarChart({
  data,
  height = 180,
  color = 'var(--primary)',
  valueLabels = true,
  formatValue = String,
  className,
  ariaLabel,
}: BarChartProps): React.JSX.Element {
  const width = 100 * Math.max(data.length, 1);
  const top = 18;
  const bottom = 26;
  const plot = height - top - bottom;
  const max = niceMax(data.map((d) => d.value));
  const slot = width / Math.max(data.length, 1);
  const barWidth = Math.min(48, slot * 0.6);
  const ticks = [0, 0.25, 0.5, 0.75, 1];
  return (
    <figure className={cn('w-full', className)}>
      <svg
        viewBox={`0 0 ${String(width)} ${String(height)}`}
        role="img"
        aria-label={ariaLabel}
        className="h-auto w-full"
        preserveAspectRatio="none"
      >
        {ticks.map((t) => (
          <line
            key={t}
            x1={0}
            x2={width}
            y1={top + plot - plot * t}
            y2={top + plot - plot * t}
            stroke="currentColor"
            strokeOpacity={0.12}
            strokeWidth={1}
          />
        ))}
        {data.map((d, i) => {
          const h = (d.value / max) * plot;
          const x = i * slot + (slot - barWidth) / 2;
          const y = top + plot - h;
          return (
            <g key={`${d.label}-${String(i)}`}>
              <rect
                className="chart-bar"
                x={x}
                y={y}
                width={barWidth}
                height={h}
                rx={4}
                fill={color}
                opacity={0.9}
                style={{ animationDelay: `${String(i * 60)}ms` }}
              >
                <title>{`${d.label}: ${String(d.value)}`}</title>
              </rect>
              {valueLabels ? (
                <text
                  x={x + barWidth / 2}
                  y={y - 5}
                  textAnchor="middle"
                  fontSize={11}
                  fill="currentColor"
                  opacity={0.8}
                >
                  {formatValue(d.value)}
                </text>
              ) : null}
              <text
                x={i * slot + slot / 2}
                y={height - 8}
                textAnchor="middle"
                fontSize={11}
                fill="currentColor"
                opacity={0.7}
              >
                {d.label}
              </text>
            </g>
          );
        })}
      </svg>
      <figcaption className="sr-only">
        {data.map((d) => `${d.label}: ${String(d.value)}`).join(', ')}
      </figcaption>
    </figure>
  );
}

interface LineChartProps {
  data: ChartPoint[];
  height?: number;
  color?: string;
  /** Fill the area under the line. */
  area?: boolean;
  /** How a value is written above its point. */
  formatValue?: (value: number) => string;
  className?: string;
  ariaLabel: string;
}

/** A single series over time, optionally filled as an area. */
export function LineChart({
  data,
  height = 180,
  color = 'var(--primary)',
  area = false,
  formatValue = String,
  className,
  ariaLabel,
}: LineChartProps): React.JSX.Element {
  const width = 600;
  const left = 8;
  const right = 8;
  const top = 18;
  const bottom = 26;
  const plot = height - top - bottom;
  const inner = width - left - right;
  const max = niceMax(data.map((d) => d.value));
  const step = data.length > 1 ? inner / (data.length - 1) : 0;
  const points = data.map((d, i) => ({
    x: left + (data.length > 1 ? i * step : inner / 2),
    y: top + plot - (d.value / max) * plot,
    ...d,
  }));
  const path = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${String(p.x)},${String(p.y)}`).join(' ');
  const areaPath =
    points.length > 0
      ? `${path} L${String(points[points.length - 1]?.x ?? 0)},${String(top + plot)} L${String(points[0]?.x ?? 0)},${String(top + plot)} Z`
      : '';
  return (
    <figure className={cn('w-full', className)}>
      <svg
        viewBox={`0 0 ${String(width)} ${String(height)}`}
        role="img"
        aria-label={ariaLabel}
        className="h-auto w-full"
      >
        {[0, 0.5, 1].map((t) => (
          <line
            key={t}
            x1={left}
            x2={width - right}
            y1={top + plot - plot * t}
            y2={top + plot - plot * t}
            stroke="currentColor"
            strokeOpacity={0.12}
          />
        ))}
        {area && areaPath ? <path className="chart-area" d={areaPath} fill={color} opacity={0.15} /> : null}
        {path ? (
          <path
            className="chart-line"
            pathLength={1}
            d={path}
            fill="none"
            stroke={color}
            strokeWidth={2.5}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        ) : null}
        {points.map((p) => (
          <g key={p.label}>
            <circle className="chart-dot" cx={p.x} cy={p.y} r={4} fill={color}>
              <title>{`${p.label}: ${String(p.value)}`}</title>
            </circle>
            <text x={p.x} y={p.y - 9} textAnchor="middle" fontSize={11} fill="currentColor" opacity={0.8}>
              {formatValue(p.value)}
            </text>
            <text x={p.x} y={height - 8} textAnchor="middle" fontSize={11} fill="currentColor" opacity={0.7}>
              {p.label}
            </text>
          </g>
        ))}
      </svg>
      <figcaption className="sr-only">
        {data.map((d) => `${d.label}: ${String(d.value)}`).join(', ')}
      </figcaption>
    </figure>
  );
}

interface DonutChartProps {
  data: ChartPoint[];
  /** Text in the middle, e.g. the total. */
  centerLabel?: string;
  centerValue?: string | number;
  size?: number;
  className?: string;
  ariaLabel: string;
}

/** Proportions as a ring, with a legend that also carries the figures. */
export function DonutChart({
  data,
  centerLabel,
  centerValue,
  size = 160,
  className,
  ariaLabel,
}: DonutChartProps): React.JSX.Element {
  const total = data.reduce((sum, d) => sum + d.value, 0);
  const radius = 42;
  const stroke = 16;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  return (
    <figure className={cn('flex flex-wrap items-center gap-6', className)}>
      <svg viewBox="0 0 100 100" width={size} height={size} role="img" aria-label={ariaLabel}>
        <circle
          cx={50}
          cy={50}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeOpacity={0.1}
          strokeWidth={stroke}
        />
        {data.map((d, i) => {
          const fraction = total > 0 ? d.value / total : 0;
          const dash = fraction * circumference;
          const element = (
            <circle
              key={d.label}
              className="chart-arc"
              style={{ animationDelay: `${String(i * 90)}ms` }}
              cx={50}
              cy={50}
              r={radius}
              fill="none"
              stroke={d.color ?? chartColor(i)}
              strokeWidth={stroke}
              strokeDasharray={`${String(dash)} ${String(circumference - dash)}`}
              strokeDashoffset={-offset}
              transform="rotate(-90 50 50)"
            >
              <title>{`${d.label}: ${String(d.value)}`}</title>
            </circle>
          );
          offset += dash;
          return element;
        })}
        {centerValue !== undefined ? (
          <text x={50} y={49} textAnchor="middle" fontSize={16} fontWeight={600} fill="currentColor">
            {centerValue}
          </text>
        ) : null}
        {centerLabel ? (
          <text x={50} y={62} textAnchor="middle" fontSize={7} fill="currentColor" opacity={0.7}>
            {centerLabel}
          </text>
        ) : null}
      </svg>
      <ul className="space-y-1 text-sm">
        {data.map((d, i) => (
          <li key={d.label} className="flex items-center gap-2">
            <span
              className="inline-block size-3 rounded-sm"
              style={{ background: d.color ?? chartColor(i) }}
              aria-hidden
            />
            <span className="text-muted-foreground">{d.label}</span>
            <span className="tabular-nums">
              {d.value}
              {total > 0 ? ` (${String(Math.round((d.value / total) * 100))}%)` : ''}
            </span>
          </li>
        ))}
      </ul>
    </figure>
  );
}

interface GaugeProps {
  value: number;
  label: string;
  className?: string;
}

/** A percentage as a horizontal gauge with the number beside it. */
export function Gauge({ value, label, className }: GaugeProps): React.JSX.Element {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div className={cn('space-y-1', className)}>
      <div className="flex items-center justify-between text-sm">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium tabular-nums">{clamped}%</span>
      </div>
      <div
        className="bg-muted h-2 overflow-hidden rounded-full"
        role="meter"
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label}
      >
        <div
          className="h-full rounded-full transition-[width] duration-700 ease-out"
          style={{ width: `${String(clamped)}%`, background: 'var(--primary)' }}
        />
      </div>
    </div>
  );
}
