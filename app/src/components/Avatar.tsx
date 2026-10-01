import { Text, View } from 'react-native';
import { F } from '../theme';

export function Avatar({ initials, hue, size = 40, ring = false }: { initials: string; hue: number; size?: number; ring?: boolean }) {
  return (
    <View
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
        backgroundColor: `hsl(${hue}, 75%, 91%)`,
        alignItems: 'center',
        justifyContent: 'center',
        borderWidth: ring ? 2 : 0,
        borderColor: '#fff',
      }}
    >
      <Text style={{ fontFamily: F.semibold, fontSize: size * 0.36, color: `hsl(${hue}, 45%, 32%)`, letterSpacing: 0.3 }}>
        {initials}
      </Text>
    </View>
  );
}
