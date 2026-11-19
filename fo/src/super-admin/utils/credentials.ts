import * as Crypto from 'expo-crypto';

export async function generateTemporaryPassword() {
  const upper = 'ABCDEFGHJKLMNPQRSTUVWXYZ';
  const lower = 'abcdefghijkmnopqrstuvwxyz';
  const digits = '23456789';
  const special = '!@#$%&*?';
  const all = upper + lower + digits + special;
  const bytes = await Crypto.getRandomBytesAsync(20);
  const pick = (pool: string, n: number) => pool[bytes[n] % pool.length];
  const chars = [pick(upper, 0), pick(lower, 1), pick(digits, 2), pick(special, 3)];
  for (let i = 4; i < 16; i++) chars.push(pick(all, i));
  for (let i = chars.length - 1; i > 0; i--) {
    const j = bytes[(i + 4) % bytes.length] % (i + 1);
    [chars[i], chars[j]] = [chars[j], chars[i]];
  }
  return chars.join('');
}
