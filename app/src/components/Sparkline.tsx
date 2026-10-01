import { Canvas, Line, Path, Rect, Skia, vec } from '@shopify/react-native-skia';
import { useMemo } from 'react';
import type { TelemetryPoint } from '../lib/types';
import { C } from '../theme';

/** Vibration sparkline with ISO 10816 bands (good < 2.8, warning ≤ 7.1, alarm above). */
export function VibrationSparkline({ series, width, height = 84 }: { series: TelemetryPoint[]; width: number; height?: number }) {
  const max = Math.max(10, ...series.map((p) => p.v));
  const y = (v: number) => height - (v / max) * height;
  const path = useMemo(() => {
    const p = Skia.Path.Make();
    series.forEach((pt, i) => {
      const x = (i / Math.max(1, series.length - 1)) * width;
      if (i === 0) p.moveTo(x, y(pt.v));
      else p.lineTo(x, y(pt.v));
    });
    return p;
  }, [series, width]);
  return (
    <Canvas style={{ width, height }}>
      <Rect x={0} y={y(max)} width={width} height={y(7.1) - y(max)} color={C.criticalBg} />
      <Rect x={0} y={y(7.1)} width={width} height={y(2.8) - y(7.1)} color={C.amberBg} />
      <Rect x={0} y={y(2.8)} width={width} height={height - y(2.8)} color={C.greenBg} />
      <Line p1={vec(0, y(7.1))} p2={vec(width, y(7.1))} color="rgba(229,72,77,0.35)" strokeWidth={1} />
      <Path path={path} color={C.ink} style="stroke" strokeWidth={2} strokeJoin="round" strokeCap="round" />
    </Canvas>
  );
}
