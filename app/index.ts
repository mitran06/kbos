import 'react-native-get-random-values';
import debug from 'debug';
import { LogBox } from 'react-native';

debug.disable('rn-webrtc:*');
LogBox.ignoreLogs([
  '`new NativeEventEmitter()` was called with a non-null argument without the required `addListener` method.',
  '`new NativeEventEmitter()` was called with a non-null argument without the required `removeListeners` method.',
]);

import 'expo-router/entry';
