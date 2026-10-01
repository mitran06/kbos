import { useEffect } from 'react';
import { View } from 'react-native';
import Animated, { Easing, useAnimatedStyle, useSharedValue, withRepeat, withTiming, type SharedValue } from 'react-native-reanimated';

const BARS = [0.55, 0.85, 1, 0.75, 0.95, 0.6, 0.8];

function Bar({ i, level, t, color }: { i: number; level: SharedValue<number>; t: SharedValue<number>; color: string }) {
  const style = useAnimatedStyle(() => {
    const wobble = 0.5 + 0.5 * Math.sin(t.get() * Math.PI * 2 * 3 + i * 1.7);
    const l = Math.min(1, level.get() * 4);
    const h = 0.18 + l * BARS[i]! * (0.55 + 0.45 * wobble);
    return { transform: [{ scaleY: h }] };
  });
  return <Animated.View style={[{ width: 4, height: 30, borderRadius: 2, backgroundColor: color, marginHorizontal: 2.5 }, style]} />;
}

/** Live waveform from an audio level shared value; all on the UI thread. */
export function Waveform({ level, color }: { level: SharedValue<number>; color: string }) {
  const t = useSharedValue(0);
  useEffect(() => {
    t.set(withRepeat(withTiming(1, { duration: 1200, easing: Easing.linear }), -1, false));
  }, [t]);
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', height: 32 }}>
      {BARS.map((_, i) => (
        <Bar key={i} i={i} level={level} t={t} color={color} />
      ))}
    </View>
  );
}
