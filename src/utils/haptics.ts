import { Haptics, ImpactStyle } from '@capacitor/haptics';

export async function hapticLight() {
  try { await Haptics.impact({ style: ImpactStyle.Light }); } catch { /* non-mobile */ }
}

export async function hapticMedium() {
  try { await Haptics.impact({ style: ImpactStyle.Medium }); } catch { /* non-mobile */ }
}

export async function hapticHeavy() {
  try { await Haptics.impact({ style: ImpactStyle.Heavy }); } catch { /* non-mobile */ }
}
