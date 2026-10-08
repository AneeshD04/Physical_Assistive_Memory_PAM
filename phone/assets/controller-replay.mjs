#!/usr/bin/env node
// Node entry for the browser controller port: `node phone/assets/controller-replay.mjs trace.json`
// trace.json is either a JSON list of samples or an object with a "samples" key.
// Prints replay() as compact JSON (keys sorted recursively, no spaces) plus a
// newline, byte-for-byte what `python3 -m perception.episode_controller trace.json`
// prints. A controller Error prints "error: <message>" to stderr and exits 1; a
// usage error exits 2. No dependencies beyond Node's own fs module.
import { readFileSync } from 'node:fs';
import { replay } from './controller.js';

// Stable stringify: object keys sorted (code-unit order, identical to Python's
// sort_keys for the ASCII keys this output has), arrays in order, no whitespace.
export function stableStringify(value) {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`;
  return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(',')}}`;
}

function main(argv) {
  if (argv.length !== 1) {
    process.stderr.write('usage: node phone/assets/controller-replay.mjs trace.json\n');
    return 2;
  }
  let data;
  try {
    data = JSON.parse(readFileSync(argv[0], 'utf8'));
  } catch (error) {
    process.stderr.write(`error: ${error.code === 'ENOENT' ? 'trace file not found' : 'trace file is not valid JSON'}\n`);
    return 1;
  }
  const samples = data !== null && typeof data === 'object' && !Array.isArray(data) ? data.samples ?? null : data;
  let result;
  try {
    result = replay(samples);
  } catch (error) {
    process.stderr.write(`error: ${error.message}\n`);
    return 1;
  }
  process.stdout.write(`${stableStringify(result)}\n`);
  return 0;
}

process.exitCode = main(process.argv.slice(2));
