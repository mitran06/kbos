import { Image } from 'expo-image';
import * as Haptics from 'expo-haptics';
import { useEffect } from 'react';
import { Pressable, Text, View } from 'react-native';
import Animated, {
  FadeIn,
  FadeInDown,
  FadeInRight,
  FadeOut,
  LinearTransition,
  useAnimatedStyle,
  useSharedValue,
  withSequence,
  withTiming,
} from 'react-native-reanimated';
import { absUrl } from '../lib/api';
import type { Draft, TicketSummary } from '../lib/types';
import { voice } from '../voice/session';
import { C, EASE_OUT, F, severityColor, shadow } from '../theme';
import { MachineChip, Pill } from './Badges';

function Field({ label, value }: { label: string; value: string | null }) {
  const wash = useSharedValue(0);
  useEffect(() => {
    if (value) wash.set(withSequence(withTiming(1, { duration: 120 }), withTiming(0, { duration: 600, easing: EASE_OUT })));
  }, [value, wash]);
  const washStyle = useAnimatedStyle(() => ({ opacity: wash.get() }));
  return (
    <View style={{ paddingVertical: 7, borderRadius: 10, overflow: 'hidden' }}>
      <Animated.View style={[{ position: 'absolute', left: -6, right: -6, top: 0, bottom: 0, backgroundColor: '#EEF2FF', borderRadius: 10 }, washStyle]} />
      <Text style={{ fontFamily: F.medium, fontSize: 11.5, color: C.ink3, letterSpacing: 0.5, textTransform: 'uppercase' }}>{label}</Text>
      {value ? (
        <Animated.Text key={value} entering={FadeInRight.duration(260).easing(EASE_OUT)} style={{ fontFamily: F.medium, fontSize: 15.5, color: C.ink, marginTop: 2 }}>
          {value}
        </Animated.Text>
      ) : (
        <View style={{ height: 10, width: 90, borderRadius: 5, backgroundColor: C.chip, marginTop: 7 }} />
      )}
    </View>
  );
}

const show = (v: string | null | undefined) => (v && v.toLowerCase() !== 'not given' ? v : v ? 'Not given' : null);

export function DraftCard({ draft }: { draft: Draft }) {
  const sev = draft.severity ? severityColor(draft.severity) : null;
  const running = draft.machine_running === null || draft.machine_running === undefined ? null : draft.machine_running ? 'Machine running' : 'Machine stopped';
  return (
    <Animated.View
      entering={FadeInDown.duration(300).easing(EASE_OUT).withInitialValues({ transform: [{ translateY: 12 }, { scale: 0.98 }] })}
      exiting={FadeOut.duration(150)}
      layout={LinearTransition.duration(220)}
      style={[{ backgroundColor: C.card, borderRadius: 22, padding: 18, marginBottom: 14 }, shadow]}
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        <Text style={{ fontFamily: F.semibold, fontSize: 13, color: C.ink3, letterSpacing: 0.6 }}>DRAFT</Text>
        {draft.machine_code && <MachineChip code={draft.machine_code} />}
        <View style={{ flex: 1 }} />
        {sev && draft.severity && (
          <Animated.View key={draft.severity} entering={FadeIn.duration(200)}>
            <Pill label={draft.severity[0]!.toUpperCase() + draft.severity.slice(1)} fg={sev.fg} bg={sev.bg} strong />
          </Animated.View>
        )}
      </View>
      <Field label="Title" value={draft.title} />
      <Field label="Symptom" value={show(draft.symptom)} />
      <View style={{ flexDirection: 'row', gap: 14 }}>
        <View style={{ flex: 1 }}>
          <Field label="Since" value={show(draft.since)} />
        </View>
        <View style={{ flex: 1 }}>
          <Field label="Production" value={running} />
        </View>
      </View>
      <Field label="Context" value={show(draft.context)} />
      {draft.related_ticket_key && (
        <Animated.View entering={FadeIn.duration(220)} style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 6 }}>
          <Text style={{ fontFamily: F.medium, color: C.ink2, fontSize: 13 }}>Same problem as</Text>
          <Pill label={draft.related_ticket_key} fg={C.amber} bg={C.amberBg} strong />
        </Animated.View>
      )}
      {draft.photos.length > 0 && (
        <View style={{ flexDirection: 'row', gap: 8, marginTop: 10 }}>
          {draft.photos.map((p) => (
            <Animated.View key={p.id} entering={FadeInDown.springify().duration(400)}>
              <Image source={{ uri: absUrl(p.url) }} style={{ width: 64, height: 64, borderRadius: 12 }} contentFit="cover" />
            </Animated.View>
          ))}
        </View>
      )}
      <View style={{ flexDirection: 'row', gap: 10, marginTop: 16 }}>
        <Pressable
          onPress={() => {
            Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
            voice.send('draft.discard');
          }}
          style={({ pressed }) => ({ flex: 1, paddingVertical: 13, borderRadius: 14, backgroundColor: C.chip, alignItems: 'center', transform: [{ scale: pressed ? 0.97 : 1 }] })}
        >
          <Text style={{ fontFamily: F.semibold, color: C.ink2, fontSize: 15 }}>Discard</Text>
        </Pressable>
        <Pressable
          disabled={!draft.machine_code || !draft.symptom}
          onPress={() => {
            Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
            voice.send('draft.file');
          }}
          style={({ pressed }) => ({
            flex: 2,
            paddingVertical: 13,
            borderRadius: 14,
            backgroundColor: C.ink,
            alignItems: 'center',
            opacity: !draft.machine_code || !draft.symptom ? 0.35 : 1,
            transform: [{ scale: pressed ? 0.97 : 1 }],
          })}
        >
          <Text style={{ fontFamily: F.semibold, color: '#fff', fontSize: 15 }}>File ticket</Text>
        </Pressable>
      </View>
    </Animated.View>
  );
}

export function FiledCard({ t }: { t: TicketSummary }) {
  const who = t.assignees.map((a) => a.name.split(' ')[0]).join(' & ') || 'nobody yet';
  return (
    <Animated.View
      entering={FadeInDown.duration(320).easing(EASE_OUT).withInitialValues({ transform: [{ translateY: 10 }, { scale: 0.97 }] })}
      exiting={FadeOut.duration(150)}
      style={[{ backgroundColor: C.card, borderRadius: 22, padding: 18, marginBottom: 14, flexDirection: 'row', alignItems: 'center', gap: 14 }, shadow]}
    >
      <View style={{ width: 44, height: 44, borderRadius: 22, backgroundColor: C.greenBg, alignItems: 'center', justifyContent: 'center' }}>
        <Text style={{ fontSize: 22, color: C.green, fontFamily: F.bold }}>✓</Text>
      </View>
      <View style={{ flex: 1 }}>
        <Text style={{ fontFamily: F.semibold, fontSize: 16, color: C.ink }}>Filed · {t.key}</Text>
        <Text style={{ fontFamily: F.regular, fontSize: 13.5, color: C.ink2, marginTop: 2 }}>
          Assigned to {who}
          {t.related_keys.length ? ` · linked to ${t.related_keys.join(', ')}` : ''}
        </Text>
      </View>
    </Animated.View>
  );
}
