import { useRef, useState } from 'react';
import { Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import { PipecatClient } from '@pipecat-ai/client-js';
import { RNSmallWebRTCTransport } from '@pipecat-ai/react-native-small-webrtc-transport';
import { DailyMediaManager } from '@pipecat-ai/react-native-daily-media-manager';

export default function Spike() {
  const [url, setUrl] = useState('http://10.54.52.211:7860');
  const [log, setLog] = useState<string[]>([]);
  const [state, setState] = useState('disconnected');
  const client = useRef<PipecatClient | null>(null);
  const add = (s: string) => {
    console.log('[spike]', s);
    setLog((l) => [s, ...l].slice(0, 60));
  };

  const connect = async () => {
    const c = new PipecatClient({
      transport: new RNSmallWebRTCTransport({ mediaManager: new DailyMediaManager() }),
      enableMic: true,
      enableCam: false,
      callbacks: {
        onTransportStateChanged: (s) => setState(s),
        onConnected: () => c.updateMic('SPEAKERPHONE'),
        onBotReady: () => add('bot ready'),
        onUserTranscript: (t) => t.final && add(`you: ${t.text}`),
        onBotOutput: (o) => o.spoken_status === 'completed' && add(`kb: ${o.text}`),
        onServerMessage: (d) => add(`server msg: ${JSON.stringify(d)}`),
        onError: (e) => add(`error: ${JSON.stringify(e)}`),
      },
    });
    client.current = c;
    try {
      await c.initDevices();
      await c.startBotAndConnect({
        endpoint: `${url}/start`,
        requestData: { transport: 'webrtc', enableDefaultIceServers: false, body: { device_id: 'spike' } },
      });
    } catch (e) {
      add(`connect failed: ${String(e)}`);
    }
  };

  return (
    <View style={{ flex: 1, paddingTop: 60, paddingHorizontal: 16, backgroundColor: '#F7F7F5' }}>
      <Text style={{ fontSize: 28, fontWeight: '700' }}>KBOS spike</Text>
      <TextInput value={url} onChangeText={setUrl} style={{ borderWidth: 1, borderColor: '#ccc', padding: 8, marginVertical: 12 }} />
      <Text testID="state">state: {state}</Text>
      <View style={{ flexDirection: 'row', gap: 12, marginVertical: 12 }}>
        <Pressable onPress={connect} style={{ backgroundColor: '#111', padding: 14, borderRadius: 10 }}>
          <Text style={{ color: '#fff' }}>Connect</Text>
        </Pressable>
        <Pressable onPress={() => client.current?.disconnect()} style={{ backgroundColor: '#999', padding: 14, borderRadius: 10 }}>
          <Text style={{ color: '#fff' }}>Leave</Text>
        </Pressable>
      </View>
      <ScrollView>{log.map((l, i) => <Text key={i} style={{ marginBottom: 4 }}>{l}</Text>)}</ScrollView>
    </View>
  );
}
