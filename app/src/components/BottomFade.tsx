import { Canvas, LinearGradient, Rect, vec } from '@shopify/react-native-skia';
import { useWindowDimensions } from 'react-native';
import { C } from '../theme';

/** Fades content out under the docked orb / pill so they never sit on top of card text. */
export function BottomFade({ height }: { height: number }) {
  const { width } = useWindowDimensions();
  return (
    <Canvas style={{ position: 'absolute', left: 0, right: 0, bottom: 0, height }} pointerEvents="none">
      <Rect x={0} y={0} width={width} height={height}>
        <LinearGradient start={vec(0, 0)} end={vec(0, height * 0.55)} colors={['rgba(247,247,245,0)', C.bg]} />
      </Rect>
    </Canvas>
  );
}
