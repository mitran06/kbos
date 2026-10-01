import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, ScrollView, Switch, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { api } from '../lib/api';
import { saveServerUrl } from '../lib/config';
import { useApp } from '../state/store';
import { C, F, shadow } from '../theme';

export default function Settings() {
  const insets = useSafeAreaInsets();
  const serverUrl = useApp((s) => s.serverUrl);
  const voiceStatus = useApp((s) => s.voice);
  const latency = useApp((s) => s.latency);
  const typeMode = useApp((s) => s.typeMode);
  const [url, setUrl] = useState(serverUrl);
  const [check, setCheck] = useState<string>('');

  const save = async () => {
    const clean = url.trim().replace(/\/+$/, '');
    await saveServerUrl(clean);
    useApp.getState().set({ serverUrl: clean });
    try {
      await api.health();
      setCheck('Connected ✓');
    } catch (e) {
      setCheck(`Can't reach it: ${String(e)}`);
    }
  };

  return (
    <ScrollView style={{ flex: 1, backgroundColor: C.bg }} contentContainerStyle={{ padding: 20, paddingTop: insets.top + 20, paddingBottom: insets.bottom + 30 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center' }}>
        <Text style={{ fontFamily: F.bold, fontSize: 26, color: C.ink, flex: 1 }}>Settings</Text>
        <Pressable onPress={() => router.back()} hitSlop={12}>
          <Text style={{ fontFamily: F.semibold, fontSize: 16, color: C.ink2 }}>Done</Text>
        </Pressable>
      </View>
      <View style={[{ backgroundColor: C.card, borderRadius: 18, padding: 16, marginTop: 20 }, shadow]}>
        <Text style={{ fontFamily: F.medium, color: C.ink3, fontSize: 13 }}>Server URL</Text>
        <TextInput
          value={url}
          onChangeText={setUrl}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          style={{ fontFamily: F.regular, fontSize: 16, color: C.ink, borderBottomWidth: 1, borderColor: C.line, paddingVertical: 8 }}
        />
        <Pressable onPress={save} style={{ marginTop: 12, backgroundColor: C.ink, borderRadius: 12, paddingVertical: 11, alignItems: 'center' }}>
          <Text style={{ fontFamily: F.semibold, color: '#fff' }}>Save & test</Text>
        </Pressable>
        {!!check && <Text style={{ fontFamily: F.regular, color: C.ink2, marginTop: 10 }}>{check}</Text>}
        <Text style={{ fontFamily: F.regular, color: C.ink3, marginTop: 10, fontSize: 13 }}>Voice: {voiceStatus}</Text>
      </View>
      <View style={[{ backgroundColor: C.card, borderRadius: 18, padding: 16, marginTop: 14, flexDirection: 'row', alignItems: 'center' }, shadow]}>
        <Text style={{ fontFamily: F.medium, color: C.ink, fontSize: 15, flex: 1 }}>Type instead of talk</Text>
        <Switch value={typeMode} onValueChange={(v) => useApp.getState().set({ typeMode: v })} />
      </View>
      <View style={[{ backgroundColor: C.card, borderRadius: 18, padding: 16, marginTop: 14 }, shadow]}>
        <Text style={{ fontFamily: F.medium, color: C.ink3, fontSize: 13, marginBottom: 8 }}>Last turn latency</Text>
        {latency.length === 0 && <Text style={{ fontFamily: F.regular, color: C.ink3 }}>No turns yet.</Text>}
        {latency.map((l, i) => (
          <Text key={i} style={{ fontFamily: 'monospace', fontSize: 12.5, color: C.ink2 }}>
            {l}
          </Text>
        ))}
      </View>
    </ScrollView>
  );
}
