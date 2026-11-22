#!/usr/bin/env node
'use strict';
/* onboarding-atlas installer. Copies files only: no network, no sudo, no postinstall hooks. */
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const PKG_ROOT = path.resolve(__dirname, '..');
const VERSION = require(path.join(PKG_ROOT, 'package.json')).version;
const SKILL_ITEMS = ['SKILL.md', 'scripts', 'templates', 'references'];

const HELP = `onboarding-atlas ${VERSION}
Generate a verified onboarding doc + interactive architecture diagram for any repo, using your coding agent.

Usage:
  npx onboarding-atlas init [dir] [options]   install the skill into a project (default: current directory)
  npx onboarding-atlas doctor                 check that Python 3.8+ is available
  npx onboarding-atlas --version

Options for init (default: all three project installs):
  --claude          .claude/skills/onboarding-atlas            (Claude Code)
  --codex           .agents/skills/onboarding-atlas + AGENTS.md note (Codex and other AGENTS.md agents)
  --cursor          .agents/skills/onboarding-atlas + .cursor/rules/onboarding-atlas.mdc (Cursor)
  --global-claude   ~/.claude/skills/onboarding-atlas          (Claude Code, every project)
  --dry-run         show what would be written, change nothing
`;

function die(msg, code) { console.error('onboarding-atlas: ' + msg); process.exit(code || 1); }

function findPython() {
  const candidates = process.platform === 'win32'
    ? [['py', ['-3']], ['python', []], ['python3', []]]
    : [['python3', []], ['python', []]];
  for (const [cmd, pre] of candidates) {
    const r = spawnSync(cmd, pre.concat(['-c', 'import sys;print("%d.%d.%d"%sys.version_info[:3])']), { encoding: 'utf8' });
    if (r.status === 0 && r.stdout) {
      const v = r.stdout.trim();
      const [maj, min] = v.split('.').map(Number);
      return { cmd: [cmd].concat(pre).join(' '), version: v, ok: maj > 3 || (maj === 3 && min >= 8) };
    }
  }
  return null;
}

function doctor() {
  const py = findPython();
  if (!py) { console.log('Python 3.8+ NOT found. Install it from https://www.python.org/downloads/ (the skill\'s scripts need it).'); return 1; }
  console.log(`Python ${py.version} found via "${py.cmd}"` + (py.ok ? ' - OK' : ' - too old, need 3.8+'));
  return py.ok ? 0 : 1;
}

function rmrf(p) { fs.rmSync(p, { recursive: true, force: true }); }

function copySkill(dest, dry) {
  if (dry) { console.log('would install -> ' + dest); return; }
  fs.mkdirSync(dest, { recursive: true });
  for (const item of SKILL_ITEMS) {
    const from = path.join(PKG_ROOT, item), to = path.join(dest, item);
    rmrf(to);
    fs.cpSync(from, to, {
      recursive: true,
      filter: (src) => !/__pycache__|\.pyc$/.test(src),
    });
  }
  console.log('installed -> ' + dest);
}

function init(args) {
  const flags = new Set(args.filter((a) => a.startsWith('--')));
  const positional = args.filter((a) => !a.startsWith('--'));
  const known = new Set(['--claude', '--codex', '--cursor', '--global-claude', '--dry-run']);
  for (const f of flags) if (!known.has(f)) die(`unknown option ${f}\n\n${HELP}`, 2);
  if (positional.length > 1) die('give at most one target directory', 2);
  const dry = flags.has('--dry-run');
  const target = path.resolve(positional[0] || '.');
  if (!fs.existsSync(target) || !fs.statSync(target).isDirectory()) die('not a directory: ' + target, 2);

  const picked = ['--claude', '--codex', '--cursor', '--global-claude'].some((f) => flags.has(f));
  const doClaude = flags.has('--claude') || !picked;
  const doCodex = flags.has('--codex') || !picked;
  const doCursor = flags.has('--cursor') || !picked;
  const doGlobal = flags.has('--global-claude');

  if (doGlobal) copySkill(path.join(os.homedir(), '.claude', 'skills', 'onboarding-atlas'), dry);
  if (doClaude) copySkill(path.join(target, '.claude', 'skills', 'onboarding-atlas'), dry);
  if (doCodex || doCursor) copySkill(path.join(target, '.agents', 'skills', 'onboarding-atlas'), dry);

  if (doCodex) {
    const agentsMd = path.join(target, 'AGENTS.md');
    const snippet = fs.readFileSync(path.join(PKG_ROOT, 'adapters', 'AGENTS.md.snippet'), 'utf8');
    const existing = fs.existsSync(agentsMd) ? fs.readFileSync(agentsMd, 'utf8') : '';
    if (existing.includes('onboarding-atlas')) console.log('AGENTS.md already mentions onboarding-atlas (left unchanged)');
    else if (dry) console.log('would update -> ' + agentsMd);
    else { fs.appendFileSync(agentsMd, (existing && !existing.endsWith('\n') ? '\n' : '') + snippet); console.log('updated -> ' + agentsMd); }
  }
  if (doCursor) {
    const rule = path.join(target, '.cursor', 'rules', 'onboarding-atlas.mdc');
    if (dry) console.log('would install -> ' + rule);
    else {
      fs.mkdirSync(path.dirname(rule), { recursive: true });
      fs.copyFileSync(path.join(PKG_ROOT, 'adapters', 'cursor-rule.mdc'), rule);
      console.log('installed -> ' + rule);
    }
  }

  const py = findPython();
  if (!py) console.log('\nWARNING: Python 3.8+ not found. The skill\'s scripts need it: https://www.python.org/downloads/');
  else if (!py.ok) console.log(`\nWARNING: Python ${py.version} is too old; need 3.8+.`);
  console.log('\nDone. Open the project in your coding agent and say:\n  Use the onboarding-atlas skill to document this repo.');
  return 0;
}

const [cmd, ...rest] = process.argv.slice(2);
switch (cmd) {
  case 'init': case 'install': process.exit(init(rest)); break;
  case 'doctor': process.exit(doctor()); break;
  case '--version': case '-v': console.log(VERSION); break;
  case undefined: case '--help': case '-h': case 'help': console.log(HELP); break;
  default: console.error(`unknown command: ${cmd}\n`); console.error(HELP); process.exit(2);
}
