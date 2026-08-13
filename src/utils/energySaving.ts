import { Capacitor, registerPlugin } from '@capacitor/core';

interface AppSettingsPlugin {
  openBatterySettings(): Promise<void>;
}

const AppSettings = registerPlugin<AppSettingsPlugin>('AppSettings');

const DISMISSED_KEY = 'cryptosentinel_battery_opt_dismissed';

export function isBatteryBannerDismissed(): boolean {
  return localStorage.getItem(DISMISSED_KEY) === 'true';
}

export function openBatterySettings(): void {
  localStorage.setItem(DISMISSED_KEY, 'true');
  if (Capacitor.isNativePlatform()) {
    AppSettings.openBatterySettings().catch(() => {
      window.open('app-settings:', '_system');
    });
  }
}
