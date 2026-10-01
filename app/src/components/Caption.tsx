import { useEffect, useState } from 'react';
import { Text } from 'react-native';
import Animated, { FadeIn, FadeOut } from 'react-native-reanimated';
import { useApp } from '../state/store';
import { C, F } from '../theme';

/** What KB heard and said, live, just above the pill. Fades a few seconds after it settles. */
export function CaptionLine({ bottom }: { bottom: number }) {
  const caption = useApp((s) => s.caption);
  const listening = useApp((s) => s.listening);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!caption) return;
    setVisible(true);
    const t = setTimeout(() => setVisible(false), caption.who === 'kb' ? 7000 : 5000);
    return () => clearTimeout(t);
  }, [caption]);

  if (!caption || !visible || !listening) return null;
  return (
    <Animated.View
      key={`${caption.who}-${caption.at > 0 ? caption.who : ''}`}
      entering={FadeIn.duration(160)}
      exiting={FadeOut.duration(220)}
      style={{ position: 'absolute', left: 20, right: 20, bottom, alignItems: 'center' }}
      pointerEvents="none"
    >
      <Text
        numberOfLines={4}
        style={{
          fontFamily: caption.who === 'kb' ? F.medium : F.regular,
          fontSize: caption.who === 'kb' ? 18 : 16.5,
          lineHeight: caption.who === 'kb' ? 25 : 23,
          color: caption.who === 'kb' ? C.ink : C.ink3,
          textAlign: 'center',
          backgroundColor: 'rgba(247,247,245,0.94)',
          borderRadius: 16,
          paddingHorizontal: 14,
          paddingVertical: 8,
          overflow: 'hidden',
        }}
      >
        {caption.text}
      </Text>
    </Animated.View>
  );
}
