// dog-ai-dashboard/scripts/launch.js — P0.S2 D5 launch wrapper.
//
// Wraps `next dev|start` so the dashboard's bind address is governed by
// a single source of truth: `DASHBOARD_BIND` env var. Default is
// 127.0.0.1 (localhost-only); LAN binding requires explicit env-var
// override AND a second env-var double-opt-in (DASHBOARD_BIND_ALLOW_ANY)
// when the user picks 0.0.0.0 (the broadest-attack bind).
//
// Spec: tests/p0_s2_plan_v1.md §1.P3 + §1.D5 + tests/p0_s2_plan_v2.md §12.
//
// Usage:
//   node scripts/launch.js dev         # → next dev --hostname 127.0.0.1 --port 3000
//   node scripts/launch.js start       # → next start --hostname 127.0.0.1 --port 3000
//   DASHBOARD_BIND=192.168.1.5 node scripts/launch.js dev
//                                      # → with stderr WARNING block
//   DASHBOARD_BIND=0.0.0.0 node scripts/launch.js dev
//                                      # → HARD ERROR (needs DASHBOARD_BIND_ALLOW_ANY=1)
//   DASHBOARD_BIND=0.0.0.0 DASHBOARD_BIND_ALLOW_ANY=1 node scripts/launch.js dev
//                                      # → with stderr WARNING block; runs
//   node scripts/launch.js dev --dry-run
//                                      # → prints the would-be argv + exits 0

'use strict'

const { spawn } = require('child_process')
const path = require('path')

// Default bind: localhost-only single-user deployment. Future S2.X with
// TLS + reverse proxy could relax this; for now LAN exposure is a
// deliberate opt-in.
const DEFAULT_BIND = '127.0.0.1'
const DEFAULT_PORT = '3000'

// Argv-injection regex (Plan v1 §1.P3): the DASHBOARD_BIND env var feeds
// directly into Next.js's --hostname flag. Restrict to alphanumerics +
// `.`, `:`, `_`, `-` so an attacker who can influence env vars cannot
// inject additional flags via shell-metacharacter chaining (e.g.,
// `DASHBOARD_BIND="0.0.0.0 --foo bar"` would otherwise pass through).
const VALID_BIND_RE = /^[a-zA-Z0-9.:_-]+$/

function _resolveSubcommand(argv) {
  // argv = ['node', 'launch.js', 'dev'|'start', maybe '--dry-run']
  const sub = argv[2]
  if (sub !== 'dev' && sub !== 'start') {
    process.stderr.write(
      "[Launch] ERROR: subcommand must be 'dev' or 'start'; got " +
      JSON.stringify(sub) + '\n'
    )
    process.exit(2)
  }
  return sub
}

function _isDryRun(argv) {
  return argv.includes('--dry-run')
}

function _resolveBind() {
  const envBind = process.env.DASHBOARD_BIND
  if (!envBind || envBind === '') {
    return { bind: DEFAULT_BIND, isDefault: true, isLoopback: true }
  }
  // Reject anything that doesn't match the safe regex BEFORE the
  // 0.0.0.0 double-opt-in check — defense against argv-injection.
  if (!VALID_BIND_RE.test(envBind)) {
    process.stderr.write(
      "[Launch] ERROR: DASHBOARD_BIND value " + JSON.stringify(envBind) +
      " contains characters outside [a-zA-Z0-9.:_-]. Refusing to launch — " +
      "rejected to prevent argv injection into next's --hostname flag.\n"
    )
    process.exit(2)
  }

  const isLoopback =
    envBind === '127.0.0.1' || envBind === 'localhost' || envBind === '::1'

  // 0.0.0.0 = bind-all-interfaces (broadest LAN exposure). Requires a
  // SECOND env-var to confirm intent (Plan v1 §1.P3 double-opt-in).
  if (envBind === '0.0.0.0') {
    const allowAny = process.env.DASHBOARD_BIND_ALLOW_ANY
    if (allowAny !== '1') {
      process.stderr.write(
        "[Launch] ERROR: DASHBOARD_BIND=0.0.0.0 binds to ALL interfaces, " +
        "exposing the dashboard to every network the host is reachable on.\n" +
        "[Launch] ERROR: P0.S2 requires a SECOND opt-in for this bind: " +
        "set DASHBOARD_BIND_ALLOW_ANY=1 to confirm you understand.\n" +
        "[Launch] ERROR: Refusing to launch.\n"
      )
      process.exit(1)
    }
  }

  return { bind: envBind, isDefault: false, isLoopback }
}

function _printWarning(bind) {
  // 6-line WARNING block per Phase 0 §2.D5
  process.stderr.write(
    "\n" +
    "[Launch] ============================ DASHBOARD WARNING ============================\n" +
    "[Launch] WARNING: dashboard is binding to " + bind + " (NOT localhost-only).\n" +
    "[Launch] WARNING: any device on this network can now reach the dashboard.\n" +
    "[Launch] WARNING: the P0.S2 auth token still protects the API, but the\n" +
    "[Launch] WARNING: token-on-disk model assumes single-user host access.\n" +
    "[Launch] WARNING: If unintentional, unset DASHBOARD_BIND and re-launch.\n" +
    "[Launch] ===========================================================================\n" +
    "\n"
  )
}

function main() {
  const argv = process.argv
  const sub = _resolveSubcommand(argv)
  const dryRun = _isDryRun(argv)
  const { bind, isLoopback } = _resolveBind()

  if (!isLoopback) {
    _printWarning(bind)
  }

  const args = [sub, '--hostname', bind, '--port', DEFAULT_PORT]
  const cmd = 'next'

  if (dryRun) {
    // Emit the resolved argv to stdout so the test harness can assert
    // the flag shape without actually spawning next.
    process.stdout.write(
      "[Launch] dry-run: " + cmd + ' ' + args.join(' ') + '\n'
    )
    process.exit(0)
  }

  // child_process.spawn with stdio inherited so next dev|start's output
  // flows directly to the user's terminal (no buffering, no proxy layer).
  const child = spawn(cmd, args, {
    stdio: 'inherit',
    shell: process.platform === 'win32',
    // Important: pass the current env so DASHBOARD_BIND etc. are not
    // re-read by a child process — Next.js doesn't care about
    // DASHBOARD_BIND, only the resolved --hostname flag matters.
    env: process.env,
  })

  child.on('exit', (code) => process.exit(code || 0))
  child.on('error', (e) => {
    process.stderr.write("[Launch] ERROR: failed to spawn 'next': " + e.message + '\n')
    process.exit(2)
  })
}

// Export internals for tests + the platform/argv-driven entry point.
// `main()` only runs when invoked as a script (NOT when require()'d).
if (require.main === module) {
  main()
}

module.exports = {
  DEFAULT_BIND,
  DEFAULT_PORT,
  VALID_BIND_RE,
  _resolveBind,
  _resolveSubcommand,
  _printWarning,
}
