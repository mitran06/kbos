import { CameraView, useCameraPermissions } from 'expo-camera';
import * as Haptics from 'expo-haptics';
import * as ImagePicker from 'expo-image-picker';
import { Image } from 'expo-image';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, Text, View } from 'react-native';
import Animated, { FadeIn, FadeOut, SlideInDown, SlideOutDown, ZoomIn } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { api } from '../lib/api';
import { useApp } from '../state/store';
import { voice } from '../voice/session';
import { C, F } from '../theme';

export function CameraSheet() {
  const camera = useApp((s) => s.camera);
  const person = useApp((s) => s.person);
  const insets = useSafeAreaInsets();
  const [perm, requestPerm] = useCameraPermissions();
  const ref = useRef<CameraView>(null);
  const [busy, setBusy] = useState(false);
  const [thumb, setThumb] = useState<string | null>(null);

  useEffect(() => {
    if (camera && perm && !perm.granted && perm.canAskAgain) requestPerm();
    if (camera) setThumb(null);
  }, [camera, perm, requestPerm]);

  if (!camera) return null;

  const close = () => useApp.getState().set({ camera: null });

  const send = async (uri: string) => {
    if (!person) return;
    setBusy(true);
    setThumb(uri);
    try {
      const r = await api.upload(uri, voice.sessionId, person.id);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      voice.send('photo.attached', { photo_ids: [r.photo_id] });
      setTimeout(close, 450);
    } catch (e) {
      console.log('[kb] upload failed', String(e));
      setThumb(null);
    } finally {
      setBusy(false);
    }
  };

  const shoot = async () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    const pic = await ref.current?.takePictureAsync({ quality: 0.6, skipProcessing: true });
    if (pic?.uri) await send(pic.uri);
  };

  const gallery = async () => {
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 0.7 });
    if (!res.canceled && res.assets[0]) await send(res.assets[0].uri);
  };

  const skip = () => {
    Haptics.selectionAsync();
    voice.send('photo.skipped');
    close();
  };

  return (
    <Animated.View entering={FadeIn.duration(180)} exiting={FadeOut.duration(150)} style={{ position: 'absolute', left: 0, right: 0, top: 0, bottom: 0, backgroundColor: 'rgba(0,0,0,0.35)' }}>
      <Animated.View
        entering={SlideInDown.duration(340).springify().dampingRatio(0.85)}
        exiting={SlideOutDown.duration(200)}
        style={{ position: 'absolute', left: 0, right: 0, bottom: 0, backgroundColor: '#0E0F12', borderTopLeftRadius: 28, borderTopRightRadius: 28, paddingBottom: insets.bottom + 18, overflow: 'hidden' }}
      >
        <View style={{ padding: 18, flexDirection: 'row', alignItems: 'center' }}>
          <Text style={{ fontFamily: F.semibold, color: '#fff', fontSize: 16, flex: 1 }}>Add a photo</Text>
          <Pressable onPress={skip} hitSlop={12} style={{ paddingHorizontal: 14, paddingVertical: 8, borderRadius: 999, backgroundColor: 'rgba(255,255,255,0.12)' }}>
            <Text style={{ fontFamily: F.semibold, color: '#fff', fontSize: 14 }}>Skip</Text>
          </Pressable>
        </View>
        <View style={{ marginHorizontal: 14, height: 380, borderRadius: 20, overflow: 'hidden', backgroundColor: '#1C1E24' }}>
          {perm?.granted ? (
            <CameraView ref={ref} style={{ flex: 1 }} facing="back" />
          ) : (
            <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
              <Text style={{ color: '#aaa', fontFamily: F.regular }}>Camera permission needed</Text>
            </View>
          )}
          {thumb && (
            <Animated.View entering={ZoomIn.duration(220)} style={{ position: 'absolute', left: 0, right: 0, top: 0, bottom: 0, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(0,0,0,0.45)' }}>
              <Image source={{ uri: thumb }} style={{ width: 160, height: 160, borderRadius: 18 }} contentFit="cover" />
              {busy && <ActivityIndicator color="#fff" style={{ position: 'absolute' }} size="large" />}
            </Animated.View>
          )}
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 36, paddingTop: 20 }}>
          <Pressable onPress={gallery} hitSlop={10} style={{ width: 52, height: 52, borderRadius: 14, backgroundColor: 'rgba(255,255,255,0.12)', alignItems: 'center', justifyContent: 'center' }}>
            <Text style={{ color: '#fff', fontFamily: F.medium, fontSize: 12 }}>Gallery</Text>
          </Pressable>
          <Pressable
            onPress={shoot}
            disabled={busy || !perm?.granted}
            style={({ pressed }) => ({ width: 76, height: 76, borderRadius: 38, borderWidth: 4, borderColor: '#fff', alignItems: 'center', justifyContent: 'center', transform: [{ scale: pressed ? 0.94 : 1 }] })}
          >
            <View style={{ width: 60, height: 60, borderRadius: 30, backgroundColor: '#fff' }} />
          </Pressable>
          <View style={{ width: 52 }} />
        </View>
        <Text style={{ textAlign: 'center', color: C.ink3, fontFamily: F.regular, fontSize: 12.5, marginTop: 12 }}>{camera.reason}</Text>
      </Animated.View>
    </Animated.View>
  );
}
