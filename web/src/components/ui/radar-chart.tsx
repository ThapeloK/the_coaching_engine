"use client";

import { useState } from "react";
import { dimensionShort } from "@/lib/format";
import type { BarsDimension } from "@/lib/types";

export interface RadarSeries {
  id: string;
  label: string;
  values: Partial<Record<BarsDimension, number | null>>;
  color: string;
  dashed?: boolean;
}

interface RadarChartProps {
  axes: BarsDimension[];
  series: RadarSeries[];
  max?: number;
  caption?: string;
  /** Hide the numeric value labels at each axis point — the chart's picture
   * stays, the numbers go. Defaults to showing them. */
  showValues?: boolean;
}

// The viewBox is deliberately wider than the plot. Labels sit at R + 18 from
// the centre and the longest ("Communication") is about 78px at 12px type, so
// each side needs roughly 100px of margin or the words get cut off by the edge
// of the svg. The radius is unchanged: only the breathing room around it.
const W = 420;
const H = 320;
const CX = 210;
const CY = 158;
const R = 96;
const RINGS = 5;

export function RadarChart({
  axes,
  series,
  max = 5,
  caption,
  showValues = true,
}: RadarChartProps) {
  const angleFor = (i: number) => (Math.PI * 2 * i) / axes.length - Math.PI / 2;

  const pointFor = (i: number, r: number) => ({
    x: CX + r * Math.cos(angleFor(i)),
    y: CY + r * Math.sin(angleFor(i)),
  });

  const polygonPoints = (r: number) =>
    axes
      .map((_, i) => {
        const p = pointFor(i, r);
        return `${p.x.toFixed(1)},${p.y.toFixed(1)}`;
      })
      .join(" ");

  const seriesPoints = (s: RadarSeries) =>
    axes
      .map((a, i) => {
        const v = s.values[a];
        const r = v == null ? 0 : (Math.max(v, 0) / max) * R;
        const p = pointFor(i, r);
        return `${p.x.toFixed(1)},${p.y.toFixed(1)}`;
      })
      .join(" ");

  const ariaLabel = `Radar chart comparing ${series
    .map((s) => s.label)
    .join(" versus ")} across ${axes
    .map((a) => dimensionShort[a])
    .join(", ")}`;

  const primary = series[0];

  // Which spoke the pointer or the keyboard is on. Null is the resting state,
  // where the chart reads exactly as it did before.
  const [active, setActive] = useState<BarsDimension | null>(null);

  /** Both series on one axis, plus the distance between them. */
  const readingFor = (axis: BarsDimension) => {
    const values = series
      .map((s) => ({ label: s.label, color: s.color, v: s.values[axis] }))
      .filter((r): r is { label: string; color: string; v: number } =>
        typeof r.v === "number"
      );
    if (values.length < 2) return { values, gap: null as number | null };
    return {
      values,
      gap: Math.abs(values[0].v - values[1].v),
    };
  };

  return (
    <figure role="img" aria-label={ariaLabel}>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full">
        {Array.from({ length: RINGS }, (_, i) => (
          <polygon
            key={i}
            points={polygonPoints(((i + 1) / RINGS) * R)}
            fill="none"
            stroke="oklch(0.4 0.02 70 / 0.12)"
          />
        ))}

        {axes.map((axis, i) => {
          const outer = pointFor(i, R);
          const isActive = active === axis;
          return (
            <line
              key={i}
              x1={CX}
              y1={CY}
              x2={outer.x}
              y2={outer.y}
              strokeWidth={isActive ? 2 : 1}
              stroke={
                isActive
                  ? "oklch(0.45 0.06 150 / 0.55)"
                  : "oklch(0.4 0.02 70 / 0.12)"
              }
            />
          );
        })}

        {axes.map((a, i) => {
          const lp = pointFor(i, R + 18);
          const anchor =
            Math.abs(lp.x - CX) < 8 ? "middle" : lp.x > CX ? "start" : "end";
          const dy =
            lp.y < CY - 4 ? "-0.2em" : lp.y > CY + 4 ? "0.9em" : "0.35em";
          return (
            <g
              key={a}
              tabIndex={0}
              role="button"
              aria-label={`${dimensionShort[a]}: ${readingFor(a)
                .values.map((v) => `${v.label} ${v.v}`)
                .join(", ")}`}
              onMouseEnter={() => setActive(a)}
              onMouseLeave={() => setActive(null)}
              onFocus={() => setActive(a)}
              onBlur={() => setActive(null)}
              style={{ cursor: "pointer", outline: "none" }}
            >
              {/* An invisible target: text alone is a thin thing to hit, and
                  on a phone it is thinner still. */}
              <rect
                x={lp.x - (anchor === "end" ? 92 : anchor === "middle" ? 46 : 0)}
                y={lp.y - 20}
                width={92}
                height={34}
                fill="transparent"
              />
              <text
                x={lp.x}
                y={lp.y}
                textAnchor={anchor}
                dy={dy}
                fontSize={12}
                fontWeight={active === a ? 600 : 400}
                opacity={
                  active && active !== a
                    ? 0.35
                    : series.some((s) => s.values[a] != null)
                      ? 1
                      : 0.72
                }
                fill="var(--foreground)"
              >
                {dimensionShort[a]}
              </text>

              {/* The answer, only on the axis being asked about. */}
              {active === a &&
                (() => {
                  const { values, gap } = readingFor(a);
                  if (values.length === 0) return null;
                  return (
                    <text
                      x={lp.x}
                      y={lp.y}
                      textAnchor={anchor}
                      dy={lp.y < CY - 4 ? "-1.5em" : "2.1em"}
                      fontSize={11}
                    >
                      {values.map((v, k) => (
                        <tspan
                          key={v.label}
                          dx={k > 0 ? 7 : 0}
                          fill={v.color}
                          fontWeight={600}
                        >
                          {v.v.toFixed(1)}
                        </tspan>
                      ))}
                      {gap != null && (
                        <tspan dx={9} fill="var(--muted-foreground)">
                          {`gap ${gap.toFixed(1)}`}
                        </tspan>
                      )}
                    </text>
                  );
                })()}
            </g>
          );
        })}

        {series.map((s, si) =>
          axes.every((a) => s.values[a] == null) ? null : (
            <g
              key={s.id}
              className="msg-in"
              style={{ animationDelay: `${350 + si * 280}ms` }}
            >
              {!s.dashed && (
                <polygon
                  points={seriesPoints(s)}
                  fill="none"
                  stroke={s.color}
                  strokeWidth={7}
                  strokeLinejoin="round"
                  opacity={0.1}
                />
              )}
              <polygon
                points={seriesPoints(s)}
                fill={s.color}
                fillOpacity={0.14}
                stroke={s.color}
                strokeWidth={2}
                strokeLinejoin="round"
                strokeDasharray={s.dashed ? "6 4" : undefined}
                pathLength={s.dashed ? undefined : 100}
                className={s.dashed ? undefined : "radar-draw"}
                style={
                  s.dashed ? undefined : { animationDelay: `${500 + si * 280}ms` }
                }
              />
            </g>
          )
        )}

        {primary &&
          axes.map((a, i) => {
            const v = primary.values[a];
            if (v == null) return null;
            const p = pointFor(i, (v / max) * R);
            const lp = pointFor(i, (v / max) * R + 11);
            return (
              <g key={a}>
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={2.5}
                  fill={primary.color}
                  className="pop-in"
                  style={{ animationDelay: `${1100 + i * 90}ms` }}
                />
                {showValues && (
                  <text
                    x={lp.x}
                    y={lp.y}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fontSize={9.5}
                    fill={primary.color}
                    className="tabular-nums"
                  >
                    {v.toFixed(1)}
                  </text>
                )}
              </g>
            );
          })}
      </svg>

      <div className="mt-2 flex flex-wrap items-center justify-center gap-4">
        {series.map((s) => (
          <span
            key={s.id}
            className="flex items-center gap-1.5 text-xs text-muted-foreground"
          >
            <span
              className="size-2 rounded-full"
              style={{ backgroundColor: s.color }}
            />
            {s.label}
          </span>
        ))}
      </div>

      <div className="sr-only">
        <table>
          <caption>{ariaLabel}</caption>
          <thead>
            <tr>
              <th scope="col">Dimension</th>
              {series.map((s) => (
                <th key={s.id} scope="col">
                  {s.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {axes.map((a) => (
              <tr key={a}>
                <th scope="row">{dimensionShort[a]}</th>
                {series.map((s) => (
                  <td key={s.id}>
                  {s.values[a] == null
                    ? "no data"
                    : showValues
                      ? s.values[a]
                      : "not shown"}
                </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {caption && (
        <figcaption className="mt-2 text-center text-xs text-muted-foreground">
          {caption}
        </figcaption>
      )}
    </figure>
  );
}
