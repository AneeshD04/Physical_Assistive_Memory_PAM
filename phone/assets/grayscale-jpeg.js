// Small baseline, single-component JPEG encoder. Canvas JPEGs remain RGB even
// after desaturation; the wire contract requires actual grayscale JPEGs.
// This uses standard JPEG DCT/quantization and explicit canonical Huffman tables,
// not a bundled library or model. Input is an 8-bit luminance plane.
const ZIGZAG = [0,1,8,16,9,2,3,10,17,24,32,25,18,11,4,5,12,19,26,33,40,48,41,34,27,20,13,6,7,14,21,28,35,42,49,56,57,50,43,36,29,22,15,23,30,37,44,51,58,59,52,45,38,31,39,46,53,60,61,54,47,55,62,63];
const QUANT = [16,11,10,16,24,40,51,61,12,12,14,19,26,58,60,55,14,13,16,24,40,57,69,56,14,17,22,29,51,87,80,62,18,22,37,56,68,109,103,77,24,35,55,64,81,104,113,92,49,64,78,87,103,121,120,101,72,92,95,98,112,100,103,99];
const BASIS = Array.from({ length: 8 }, (_, u) => Array.from({ length: 8 }, (_, x) => .5 * (u === 0 ? Math.SQRT1_2 : 1) * Math.cos((2 * x + 1) * u * Math.PI / 16)));
const AC_VALUES = [0, 240];
for (let run = 0; run < 16; run++) for (let size = 1; size <= 10; size++) AC_VALUES.push(run * 16 + size);
const AC_CODES = new Map(AC_VALUES.map((value, code) => [value, code]));
export function encodeGrayJPEG(gray, width, height) {
  if (!(gray instanceof Uint8Array) || gray.length !== width * height || !Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1 || width > 320 || height > 320) throw new Error('Invalid analysis plane');
  const out = [255, 216];
  function segment(marker, data) { const length = data.length + 2; out.push(255, marker, length >> 8, length & 255, ...data); }
  segment(219, [0, ...ZIGZAG.map(index => QUANT[index])]);
  segment(192, [8, height >> 8, height & 255, width >> 8, width & 255, 1, 1, 17, 0]);
  // DC categories 0..11 at length 4; AC symbols at length 8. No all-ones code.
  segment(196, [0, ...Array.from({ length: 16 }, (_, i) => i === 3 ? 12 : 0), ...Array.from({ length: 12 }, (_, i) => i)]);
  segment(196, [16, ...Array.from({ length: 16 }, (_, i) => i === 7 ? AC_VALUES.length : 0), ...AC_VALUES]);
  segment(218, [1, 1, 0, 0, 63, 0]);
  let pending = 0, bitCount = 0;
  function bits(value, length) {
    for (let i = length - 1; i >= 0; i--) {
      pending = (pending << 1) | ((value >> i) & 1);
      if (++bitCount === 8) { out.push(pending); if (pending === 255) out.push(0); pending = 0; bitCount = 0; }
    }
  }
  function amplitude(value) {
    const size = value === 0 ? 0 : Math.floor(Math.log2(Math.abs(value))) + 1;
    return [size, value < 0 ? value + (1 << size) - 1 : value];
  }
  let previousDC = 0;
  const row = new Float64Array(64), coefficients = new Int16Array(64);
  for (let top = 0; top < height; top += 8) for (let left = 0; left < width; left += 8) {
    for (let y = 0; y < 8; y++) for (let u = 0; u < 8; u++) {
      let sum = 0;
      for (let x = 0; x < 8; x++) sum += (gray[Math.min(top + y, height - 1) * width + Math.min(left + x, width - 1)] - 128) * BASIS[u][x];
      row[y * 8 + u] = sum;
    }
    for (let v = 0; v < 8; v++) for (let u = 0; u < 8; u++) {
      let sum = 0;
      for (let y = 0; y < 8; y++) sum += row[y * 8 + u] * BASIS[v][y];
      coefficients[v * 8 + u] = Math.round(sum / QUANT[v * 8 + u]);
    }
    const [dcSize, dcValue] = amplitude(coefficients[0] - previousDC);
    bits(dcSize, 4); bits(dcValue, dcSize); previousDC = coefficients[0];
    let run = 0;
    for (let i = 1; i < 64; i++) {
      const value = coefficients[ZIGZAG[i]];
      if (value === 0) { run++; continue; }
      while (run >= 16) { bits(AC_CODES.get(240), 8); run -= 16; }
      const [size, encoded] = amplitude(value);
      bits(AC_CODES.get(run * 16 + size), 8); bits(encoded, size); run = 0;
    }
    if (run) bits(AC_CODES.get(0), 8);
  }
  if (bitCount) bits((1 << (8 - bitCount)) - 1, 8 - bitCount);
  out.push(255, 217);
  let binary = '';
  for (const byte of out) binary += String.fromCharCode(byte);
  return btoa(binary);
}
