import * as Haptics from 'expo-haptics';
import { useEffect, useState } from 'react';
import { Pressable, Text, TextInput, useWindowDimensions, View } from 'react-native';
import Animated, { useAnimatedStyle, useDerivedValue, useSharedValue, withDelay, withSpring, withTiming } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useApp } from '../state/store';
import { botLevel, botSpeakingSV, listeningSV, micLevel, voice } from '../voice/session';
import { C, F, shadow } from '../theme';
import { Orb } from './Orb';
import { Waveform } from './Waveform';

const ORB = 210;
const SPRING = { duration: 520, dampingRatio: 0.82 };
const PILL_H = 74;

/** The orb, and its morph into the listening pill docked at the bottom. */
export function Dock({ hasContent }: { hasContent: boolean }) {
  const { width: W, height: H } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const listening = useApp((s) => s.listening);
  const botSpeaking = useApp((s) => s.botSpeaking);
  const working = useApp((s) => s.working);
  const voiceStatus = useApp((s) => s.voice);
  const typeMode = useApp((s) => s.typeMode);
  const [typing, setTyping] = useState(false);
  const [text, setText] = useState('');

  const mode = listening ? 'pill' : hasContent ? 'dock' : 'hero';
  const pillBottom = insets.bottom + 14;
  const target = {
    hero: { x: W / 2, y: H * 0.47, s: 1 },
    dock: { x: W / 2, y: H - insets.bottom - 76, s: 0.46 },
    pill: { x: 16 + 10 + 27, y: H - pillBottom - PILL_H / 2, s: 0.28 },
  }[mode];

  const x = useSharedValue(target.x);
  const y = useSharedValue(target.y);
  const sc = useSharedValue(target.s);
  const pill = useSharedValue(0);
  const press = useSharedValue(1);

  useEffect(() => {
    x.set(withSpring(target.x, SPRING));
    y.set(withSpring(target.y, SPRING));
    sc.set(withSpring(target.s, SPRING));
    pill.set(mode === 'pill' ? withDelay(60, withSpring(1, { duration: 420, dampingRatio: 0.9 })) : withTiming(0, { duration: 180 }));
    if (mode !== 'pill') setTyping(false);
  }, [mode, target.x, target.y, target.s, x, y, sc, pill]);

  const level = useDerivedValue(() => (botSpeakingSV.get() ? botLevel.get() : listeningSV.get() ? micLevel.get() : 0));

  const orbStyle = useAnimatedStyle(() => ({
    transform: [{ translateX: x.get() - ORB / 2 }, { translateY: y.get() - ORB / 2 }, { scale: sc.get() * press.get() }],
  }));
  const pillStyle = useAnimatedStyle(() => ({
    opacity: pill.get(),
    transform: [{ translateY: (1 - pill.get()) * 24 }, { scaleX: 0.85 + 0.15 * pill.get() }],
  }));
  const waveStyle = useAnimatedStyle(() => ({ opacity: Math.max(0, pill.get() * 1.6 - 0.6) }));

  const onOrb = () => {
    if (voiceStatus !== 'ready') {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
      voice.connect({ brief: false, listen: true });
      return;
    }
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    if (listening) voice.stop();
    else voice.listen();
  };

  const status = voiceStatus !== 'ready' ? (voiceStatus === 'connecting' ? 'Connecting…' : 'Offline · tap to reconnect') : working ? 'Working…' : botSpeaking ? 'KB' : 'Listening';

  return (
    <View style={{ position: 'absolute', left: 0, right: 0, top: 0, bottom: 0 }} pointerEvents="box-none">
      <Animated.View
        pointerEvents={mode === 'pill' ? 'auto' : 'none'}
        style={[{ position: 'absolute', left: 16, right: 16, bottom: pillBottom, height: PILL_H, borderRadius: PILL_H / 2, backgroundColor: C.card }, shadow, pillStyle]}
      >
        <Pressable
          style={{ flex: 1, flexDirection: 'row', alignItems: 'center', paddingLeft: 78, paddingRight: 12 }}
          onLongPress={() => {
            Haptics.selectionAsync();
            setTyping(true);
          }}
        >
          {typing || typeMode ? (
            <TextInput
              autoFocus
              value={text}
              onChangeText={setText}
              placeholder="Type to KB…"
              placeholderTextColor={C.ink3}
              returnKeyType="send"
              onSubmitEditing={() => {
                if (text.trim()) voice.sendText(text.trim());
                setText('');
              }}
              style={{ flex: 1, fontFamily: F.regular, fontSize: 16, color: C.ink }}
            />
          ) : (
            <>
              <Text style={{ fontFamily: F.medium, color: C.ink3, fontSize: 13.5, width: 78 }}>{status}</Text>
              <Animated.View style={[{ flex: 1, alignItems: 'center' }, waveStyle]}>
                <Waveform level={level} color={botSpeaking ? '#7B6CF6' : C.ink} />
              </Animated.View>
            </>
          )}
          <Pressable
            onPress={() => {
              Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
              voice.stop();
            }}
            hitSlop={8}
            accessibilityLabel="Stop"
            style={({ pressed }) => ({ width: 50, height: 50, borderRadius: 25, backgroundColor: C.ink, alignItems: 'center', justifyContent: 'center', transform: [{ scale: pressed ? 0.94 : 1 }] })}
          >
            <View style={{ width: 16, height: 16, borderRadius: 4, backgroundColor: '#fff' }} />
          </Pressable>
        </Pressable>
      </Animated.View>

      <Animated.View style={[{ position: 'absolute', left: 0, top: 0, width: ORB, height: ORB }, orbStyle]}>
        <Pressable
          onPressIn={() => press.set(withTiming(0.97, { duration: 110 }))}
          onPressOut={() => press.set(withSpring(1, { duration: 300, dampingRatio: 0.7 }))}
          onPress={onOrb}
          accessibilityLabel={listening ? 'Stop listening' : 'Talk to KB'}
          style={{ width: ORB, height: ORB }}
        >
          <Orb size={ORB} level={level} />
        </Pressable>
      </Animated.View>
    </View>
  );
}
