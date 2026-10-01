import { BlurMask, Canvas, Circle, Group, RadialGradient, vec } from '@shopify/react-native-skia';
import { useEffect } from 'react';
import {
  Easing,
  ReduceMotion,
  useDerivedValue,
  useReducedMotion,
  useSharedValue,
  withRepeat,
  withTiming,
  type SharedValue,
} from 'react-native-reanimated';
import { ORB } from '../theme';

/**
 * KB's orb: four soft color blobs drifting inside a blurred circle. Breathes when idle and
 * swells with the live audio level (mic while listening, KB's voice while speaking).
 */
export function Orb({ size, level }: { size: number; level: SharedValue<number> }) {
  const reduced = useReducedMotion();
  const t = useSharedValue(0);
  const breath = useSharedValue(0);

  useEffect(() => {
    if (reduced) return;
    t.set(withRepeat(withTiming(1, { duration: 9000, easing: Easing.linear }), -1, false));
    breath.set(withRepeat(withTiming(1, { duration: 4000, easing: Easing.inOut(Easing.sin), reduceMotion: ReduceMotion.System }), -1, true));
  }, [reduced, t, breath]);

  const c = size / 2;
  const smooth = useSharedValue(0);
  const scale = useDerivedValue(() => {
    // smooth the level so the orb swells instead of flickering
    smooth.set(smooth.get() + (Math.min(1, level.get() * 3) - smooth.get()) * 0.18);
    return 1 + breath.get() * 0.03 + smooth.get() * 0.12;
  });
  const transform = useDerivedValue(() => [
    { translateX: c },
    { translateY: c },
    { scale: scale.get() },
    { translateX: -c },
    { translateY: -c },
  ]);

  const blob = (i: number) => {
    'worklet';
    const a = t.get() * Math.PI * 2 * (i % 2 === 0 ? 1 : -1) + (i * Math.PI) / 2;
    const r = size * (0.13 + 0.03 * Math.sin(t.get() * Math.PI * 4 + i));
    return { x: c + Math.cos(a) * r, y: c + Math.sin(a * 1.3) * r };
  };
  const b0 = useDerivedValue(() => blob(0));
  const b1 = useDerivedValue(() => blob(1));
  const b2 = useDerivedValue(() => blob(2));
  const b3 = useDerivedValue(() => blob(3));
  const x0 = useDerivedValue(() => b0.get().x);
  const y0 = useDerivedValue(() => b0.get().y);
  const x1 = useDerivedValue(() => b1.get().x);
  const y1 = useDerivedValue(() => b1.get().y);
  const x2 = useDerivedValue(() => b2.get().x);
  const y2 = useDerivedValue(() => b2.get().y);
  const x3 = useDerivedValue(() => b3.get().x);
  const y3 = useDerivedValue(() => b3.get().y);
  const blobR = size * 0.27;

  return (
    <Canvas style={{ width: size, height: size }}>
      <Group transform={transform}>
        <Circle cx={c} cy={c} r={size * 0.36} color="#C9D6FF" opacity={0.55}>
          <BlurMask blur={size * 0.08} style="normal" />
        </Circle>
        <Group>
          <Circle cx={x0} cy={y0} r={blobR} color={ORB[0]} opacity={0.9}>
            <BlurMask blur={size * 0.09} style="normal" />
          </Circle>
          <Circle cx={x1} cy={y1} r={blobR} color={ORB[1]} opacity={0.85}>
            <BlurMask blur={size * 0.09} style="normal" />
          </Circle>
          <Circle cx={x2} cy={y2} r={blobR * 0.9} color={ORB[2]} opacity={0.8}>
            <BlurMask blur={size * 0.09} style="normal" />
          </Circle>
          <Circle cx={x3} cy={y3} r={blobR * 0.9} color={ORB[3]} opacity={0.85}>
            <BlurMask blur={size * 0.09} style="normal" />
          </Circle>
        </Group>
        <Circle cx={c} cy={c} r={size * 0.3}>
          <RadialGradient c={vec(c - size * 0.08, c - size * 0.1)} r={size * 0.32} colors={['rgba(255,255,255,0.75)', 'rgba(255,255,255,0)']} />
        </Circle>
      </Group>
    </Canvas>
  );
}
