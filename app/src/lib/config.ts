import AsyncStorage from '@react-native-async-storage/async-storage';

const KEY = 'kbos.serverUrl';
// adb reverse makes localhost reach the laptop over USB; on the demo hotspot set the laptop IP in Settings.
export const DEFAULT_SERVER = process.env.EXPO_PUBLIC_SERVER_URL ?? 'http://localhost:7860';

export async function loadServerUrl(): Promise<string> {
  try {
    return (await AsyncStorage.getItem(KEY)) ?? DEFAULT_SERVER;
  } catch {
    return DEFAULT_SERVER;
  }
}

export async function saveServerUrl(url: string): Promise<void> {
  await AsyncStorage.setItem(KEY, url.replace(/\/+$/, ''));
}
